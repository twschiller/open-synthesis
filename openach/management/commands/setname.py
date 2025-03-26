"""Django admin command to set the site from the project settings.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/ref/contrib/sites/
"""

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Django admin command to set the site from the project settings.

    Requires the following settings: SITE_ID, SITE_NAME, and SITE_DOMAIN.
    """

    help = "Sets the site name and domain from the environment"

    def handle(self, *args, **options):
        """Handle the command invocation."""
        site_id = getattr(settings, "SITE_ID", None)
        site_name = getattr(settings, "SITE_NAME", None)
        site_domain = getattr(settings, "SITE_DOMAIN", None)

        if not site_id:
            raise CommandError("No SITE_ID specified in project settings")
        if not site_name:
            raise CommandError("No SITE_NAME specified in project settings")
        if not site_domain:
            raise CommandError("No SITE_DOMAIN specified in project settings")

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:  # pylint: disable=no-member
            raise CommandError('Site "%s" does not exist' % site_id)

        site.name = site_name
        site.domain = site_domain
        site.save()

        msg = 'Successfully configured site #{}; name: "{}"; domain: {}'.format(
            site_id,
            site_name,
            site_domain,
        )
        self.stdout.write(self.style.SUCCESS(msg))  # pylint: disable=no-member
