"""Django template context processors."""
from django.contrib.sites.models import Site


def site(dummy_request):
    """Return a template context with the current site as 'site'."""
    # NOTE: get_current caches the result from the db
    # See: https://docs.djangoproject.com/en/1.10/ref/contrib/sites/#caching-the-current-site-object
    return {'site': Site.objects.get_current()}
