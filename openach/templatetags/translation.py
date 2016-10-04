"""Django Template Localization Helper Methods.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/howto/custom-template-tags/
"""

from django.template.defaulttags import register
from django.utils.translation import to_locale, get_language


@register.simple_tag()
def get_current_locale():
    """Return the locale for the current language."""
    return to_locale(get_language())
