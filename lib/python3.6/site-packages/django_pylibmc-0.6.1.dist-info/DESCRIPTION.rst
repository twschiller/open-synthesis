================================
pylibmc cache backend for Django
================================

.. image:: https://travis-ci.org/django-pylibmc/django-pylibmc.svg
    :target: https://travis-ci.org/django-pylibmc/django-pylibmc

This package provides a memcached cache backend for Django using
`pylibmc <http://github.com/lericson/pylibmc>`_.  You want to use pylibmc because
it's fast.

Do you need django-pylibmc?
---------------------------
Django has direct support for pylibmc.  To use it, set you cache backend::

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
            'LOCATION': '127.0.0.1.11211',
        }
    }

See the
`Django documentation <https://docs.djangoproject.com/en/1.8/topics/cache/#memcached>`_
for details about using this cache backend.

Two reasons to use django-pylibmc instead are:

- You need to use the binary protocol
- You need to use a username and password to access the memcached server (such as
  with `Memcachier on Heroku <https://devcenter.heroku.com/articles/memcachier#django>`_).


Requirements
------------

django-pylibmc requires pylibmc 1.4.1 or above.  It supports Django 1.7 through
1.9, and Python versions 2.7, 3.4, and 3.5.

Installation
------------

Get it from `pypi <http://pypi.python.org/pypi/django-pylibmc>`_::

    pip install django-pylibmc

or `github <http://github.com/django-pylibmc/django-pylibmc>`_::

    pip install -e git://github.com/django-pylibmc/django-pylibmc.git#egg=django-pylibmc


Usage
-----

Your cache backend should look something like this::

    CACHES = {
        'default': {
            'BACKEND': 'django_pylibmc.memcached.PyLibMCCache',
            'LOCATION': 'localhost:11211',
            'TIMEOUT': 500,
            'BINARY': True,
            'OPTIONS': {  # Maps to pylibmc "behaviors"
                'tcp_nodelay': True,
                'ketama': True
            }
        }
    }

To use a `memcached local socket connection
<https://code.google.com/p/memcached/wiki/NewConfiguringServer#Unix_Sockets>`_,
set ``LOCATION`` to the path to the file, i.e. ``'/var/run/memcached/memcached.sock'``.

If you want to use the memcached binary protocol, set the ``BINARY`` key's
value to ``True`` as shown above.  ``BINARY`` is ``False`` by default.

If you want to control `pylibmc behaviors
<http://sendapatch.se/projects/pylibmc/behaviors.html>`_, use the
``OPTIONS``.  ``OPTIONS`` is an empty dict by default.

Pylibmc supports `compression
<http://sendapatch.se/projects/pylibmc/misc.html#compression>`_ and the
minimum size (in bytes) of values to compress can be set via the Django
setting ``PYLIBMC_MIN_COMPRESS_LEN``.  The default is ``0``, which is disabled.

Pylibmc 1.3.0 and above allows to configure compression level, which can
be set via the Django setting ``PYLIBMC_COMPRESS_LEVEL``. It accepts the
same values as the Python `zlib <https://docs.python.org/2/library/zlib.html>`_
module. Please note that pylibmc changed the default from ``1`` (``Z_BEST_SPEED``)
to ``-1`` (``Z_DEFAULT_COMPRESSION``) in 1.3.0.


Configuration with Environment Variables
----------------------------------------

Optionally, the memcached connection can be configured with environment
variables (on platforms like Heroku). To do so, declare the following
variables:

* ``MEMCACHE_SERVERS``
* ``MEMCACHE_USERNAME``
* ``MEMCACHE_PASSWORD``


Caching Timouts
---------------
When setting a cache value, memcache allows you to set an expiration for the
value. Commonly, the value is set to a timeout in seconds. However, other
values are allowed including Unix timestamps and 0 for "never expire". The
highest number of seconds is 30 days - more than that, and the value is
treated like a timestamp.

Django instead tries to work with cache timeouts in seconds after the current
time. 0 is treated as 0 seconds, meaning the item should expire immediately.
A timeout of None signals that the item should not expire. There is some
support for memcache-style Unix timestamps as well.

In the distant past (Django 1.3?), a timeout of 0 was converted to the default
timeout.

The current django-pylibmc behaviour is to pass 0 to the backend, which should
be interpreted as "never expire". Omiting the timeout will get the Django
default.

In the future, django-pylibmc will adopt the latest Django behaviour.
The safest solution for your own code is to omit the timeout parameter (and
get the default timeout), or set it to a timeout in seconds (less than 30
days). This way, your code will work when the Django behaviour is adopted.
Avoid using a timeout of 0, None, or a negative number.

Testing
-------

Install `tox <http://tox.testrun.org/>`_::

    pip install tox

Run the tests like this::

    tox

Changelog
=========

0.6.1 - 2015-12-28
------------------
- Supports Django 1.7 through 1.9
- Supports Python 2.7, 3.4, and 3.5

0.6.0 - 2015-04-01
------------------
- Requires pylibmc 1.4.1 or greater
- Supports Django 1.4 through 1.8.
- Supports Python 2.5 through 2.7, and Python 3.3 through 3.4
- In Django 1.6 and higher, when the timeout is omitted, the default
  timeout is used, rather than set to "never expire".


