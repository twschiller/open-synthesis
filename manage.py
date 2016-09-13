#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/ref/django-admin/
"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "openintel.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError:  # pragma: no cover
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            # NOTE: the django import is used by 'execute_from_command_line' below
            import django  # pylint: disable=unused-import
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )
        raise
    execute_from_command_line(sys.argv)
