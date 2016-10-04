"""Django template context processors."""
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.models import Site
from django.conf import settings


def site(dummy_request):
    """Return a template context with the current site as 'site'."""
    # NOTE: get_current caches the result from the db
    # See: https://docs.djangoproject.com/en/1.10/ref/contrib/sites/#caching-the-current-site-object
    return {'site': Site.objects.get_current()}


def meta(dummy_request):
    """Return a template context with site's social account information."""
    site_name = Site.objects.get_current().name
    return {
        'twitter_account': getattr(settings, 'TWITTER_ACCOUNT', None),
        'facebook_account': getattr(settings, 'FACEBOOK_ACCOUNT', None),
        'default_description': _("{name} is an open platform for intelligence analysis").format(name=site_name),
        'default_keywords': [_("Analysis of Competing Hypothesis"), _("ACH"), _("intelligence analysis")]
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
