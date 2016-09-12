"""Django template context processors"""
from django.contrib.sites.models import Site


def site(dummy_request):
    """Returns a template context with the current site as 'site'"""
    return {'site': Site.objects.get_current()}
