"""Django template context processors."""
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.utils.translation import ugettext_lazy as _


def site(request):
    """Return a template context with the current site as 'site'."""
    # NOTE: get_current_site caches the result from the db
    # See: https://docs.djangoproject.com/en/1.10/ref/contrib/sites/#caching-the-current-site-object
    return {'site': get_current_site(request)}


def meta(request):
    """Return a template context with site's social account information."""
    site_name = get_current_site(request)
    return {
        'twitter_account': getattr(settings, 'TWITTER_ACCOUNT', None),
        'facebook_account': getattr(settings, 'FACEBOOK_ACCOUNT', None),
        'default_description': _('{name} is an open platform for CIA-style intelligence analysis').format(name=site_name),  # nopep8
        'default_keywords': [
            _('Analysis of Competing Hypotheses'),
            _('ACH'),
            _('intelligence analysis'),
            _('current events')
        ]
    }


def invite(dummy_request):
    """Return a template context with the site's invitation configuration."""
    return {
        'invite_request_url': getattr(settings, 'INVITE_REQUEST_URL', None),
    }


def banner(dummy_request):
    """Return a template context with a the site's banner configuration."""
    return {
        'banner': getattr(settings, 'BANNER_MESSAGE', None),
    }
