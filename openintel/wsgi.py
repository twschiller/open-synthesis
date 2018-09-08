"""
WSGI config for openintel project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""
import os

from django.core.wsgi import get_wsgi_application
from django.core.cache.backends.memcached import BaseMemcachedCache

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "openintel.settings")

application = get_wsgi_application()

# Fix django closing connection to MemCachier after every request (#11331)
# https://devcenter.heroku.com/articles/django-memcache#optimize-performance
BaseMemcachedCache.close = lambda self, **kwargs: None
