"""
Memcached cache backend for Django using pylibmc.

If you want to use the binary protocol, specify `'BINARY': True` in your CACHES
settings.  The default is `False`, using the text protocol.

pylibmc behaviors can be declared as a dict in `CACHES` backend `OPTIONS`
setting.

Unlike the default Django caching backends, this backend lets you pass 0 as a
timeout, which translates to an infinite timeout in memcached.
"""
import logging
import warnings
from threading import local

from django.conf import settings
from django.core.cache.backends.base import InvalidCacheBackendError
from django.core.cache.backends.memcached import BaseMemcachedCache

try:
    import pylibmc
    from pylibmc import Error as MemcachedError
except ImportError:
    raise InvalidCacheBackendError('Could not import pylibmc.')

try:
    from django.core.cache.backends.memcached import DEFAULT_TIMEOUT
except ImportError:
    DEFAULT_TIMEOUT = None


log = logging.getLogger('django.pylibmc')


MIN_COMPRESS_LEN = getattr(settings, 'PYLIBMC_MIN_COMPRESS_LEN', 0)  # Disabled
if MIN_COMPRESS_LEN > 0 and not pylibmc.support_compression:
    MIN_COMPRESS_LEN = 0
    warnings.warn('A minimum compression length was provided but pylibmc was '
                  'not compiled with support for it.')


COMPRESS_LEVEL = getattr(settings, 'PYLIBMC_COMPRESS_LEVEL', -1)  # zlib.Z_DEFAULT_COMPRESSION
if not COMPRESS_LEVEL == -1:
    if not pylibmc.support_compression:
        warnings.warn('A compression level was provided but pylibmc was '
                      'not compiled with support for it.')
    if not pylibmc.__version__ >= '1.3.0':
        warnings.warn('A compression level was provided but pylibmc 1.3.0 '
                      'or above is required to handle this option.')


# Keyword arguments to configure compression options
# based on capabilities of a provided pylibmc library.
COMPRESS_KWARGS = {
    # Requires pylibmc 1.0 and above. Given that the minumum supported
    # version (as of now) is 1.1, the parameter is always included.
    'min_compress_len': MIN_COMPRESS_LEN,
}
if pylibmc.__version__ >= '1.3.0':
    COMPRESS_KWARGS['compress_level'] = COMPRESS_LEVEL


class PyLibMCCache(BaseMemcachedCache):

    def __init__(self, server, params, username=None, password=None):
        import os
        self._local = local()
        self.binary = int(params.get('BINARY', False))
        self._username = os.environ.get('MEMCACHE_USERNAME', username or params.get('USERNAME'))
        self._password = os.environ.get('MEMCACHE_PASSWORD', password or params.get('PASSWORD'))
        self._server = os.environ.get('MEMCACHE_SERVERS', server)
        super(PyLibMCCache, self).__init__(self._server, params, library=pylibmc,
                                           value_not_found_exception=pylibmc.NotFound)

    @property
    def _cache(self):
        # PylibMC uses cache options as the 'behaviors' attribute.
        # It also needs to use threadlocals, because some versions of
        # PylibMC don't play well with the GIL.
        client = getattr(self._local, 'client', None)
        if client:
            return client

        client_kwargs = {'binary': self.binary}
        if self._username is not None and self._password is not None:
            client_kwargs.update({
                'username': self._username,
                'password': self._password
            })
        client = self._lib.Client(self._servers, **client_kwargs)
        if self._options:
            client.behaviors = self._options

        self._local.client = client

        return client

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        """
        Special case timeout=0 to allow for infinite timeouts.
        """
        if timeout == 0:
            return timeout

        try:
            return super(PyLibMCCache, self).get_backend_timeout(timeout)
        except AttributeError:
            # ._get_memcache_timeout() will be deprecated in Django 1.9
            # It's already raising DeprecationWarning in Django 1.8
            # See: https://docs.djangoproject.com/en/1.8/internals/deprecation/#deprecation-removed-in-1-9
            return self._get_memcache_timeout(timeout)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_key(key, version=version)
        try:
            return self._cache.add(key, value,
                                   self.get_backend_timeout(timeout),
                                   **COMPRESS_KWARGS)
        except pylibmc.ServerError:
            log.error('ServerError saving %s (%d bytes)' % (key, len(str(value))),
                      exc_info=True)
            return False
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return False

    def get(self, key, default=None, version=None):
        try:
            return super(PyLibMCCache, self).get(key, default, version)
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return default

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_key(key, version=version)
        try:
            return self._cache.set(key, value,
                                   self.get_backend_timeout(timeout),
                                   **COMPRESS_KWARGS)
        except pylibmc.ServerError:
            log.error('ServerError saving %s (%d bytes)' % (key, len(str(value))),
                      exc_info=True)
            return False
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return False

    def delete(self, *args, **kwargs):
        try:
            return super(PyLibMCCache, self).delete(*args, **kwargs)
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return False

    def get_many(self, *args, **kwargs):
        try:
            return super(PyLibMCCache, self).get_many(*args, **kwargs)
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return {}

    def set_many(self, *args, **kwargs):
        try:
            return super(PyLibMCCache, self).set_many(*args, **kwargs)
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return False

    def delete_many(self, *args, **kwargs):
        try:
            return super(PyLibMCCache, self).delete_many(*args, **kwargs)
        except MemcachedError as e:
            log.error('MemcachedError: %s' % e, exc_info=True)
            return False
