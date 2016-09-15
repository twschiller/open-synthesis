"""Django template context processors."""
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
        'default_description': "{} is an open platform for intelligence analysis".format(site_name),
        'default_keywords': ["Analysis of Competing Hypothesis", "ACH", "intelligence analysis"]
    }
