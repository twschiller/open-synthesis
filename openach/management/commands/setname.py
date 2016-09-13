"""Django admin command to set the site from the environment"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.sites.models import Site
from django.conf import settings


class Command(BaseCommand):
    help = 'Sets the site name and domain from the environment'

    def handle(self, *args, **options):
        site_id = getattr(settings, 'SITE_ID', None)
        site_name = getattr(settings, 'SITE_NAME', None)
        site_domain = getattr(settings, 'SITE_DOMAIN', None)

        if not site_id:
            raise CommandError('No SITE_ID specified in project settings')
        if not site_name:
            raise CommandError('No SITE_NAME specified in project settings')
        if not site_domain:
            raise CommandError('No SITE_DOMAIN specified in project settings')

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            raise CommandError('Site "%s" does not exist' % site_id)

        site.name = site_name
        site.domain = site_domain
        site.save()

        msg = 'Successfully configured site #%s; name: "%s"; domain: %s' % (site_id, site_name, site_domain)
        self.stdout.write(self.style.SUCCESS(msg))
