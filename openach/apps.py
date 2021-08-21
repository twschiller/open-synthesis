"""openach Application Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/ref/applications/
"""
from django.apps import AppConfig


class OpenACHConfig(AppConfig):
    """Django application configuration for the Analysis of Competing Hypotheses (ACH) application.

    For more information, please see:
        https://docs.djangoproject.com/en/1.10/ref/applications/
    """

    name = "openach"
    verbose_name = "Open ACH"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        # hook up the signals
        import openach.signals  # pylint: disable=unused-import
