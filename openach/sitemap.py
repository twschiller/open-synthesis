"""Analysis of Competing Hypotheses Django application Sitemap configuration.

Sitemaps convey meta-information to web search engines/crawlers about the content on the site. For more information,
please see:
    https://docs.djangoproject.com/en/1.10/ref/contrib/sitemaps
"""
from django.contrib.sitemaps import Sitemap

from .models import Board, Evidence, Hypothesis


class BoardSitemap(Sitemap):
    """Sitemap containing metadata about ACH boards."""

    protocol = "https"
    changefreq = "daily"
    priority = 0.5

    def items(self):
        """Return all the items for the Sitemap."""
        return Board.objects.public()

    def lastmod(self, obj):  # pylint: disable=no-self-use
        """Return the last time the board or its content was structurally modified."""
        # NOTE: self parameter is required to match the Sitemap interface
        def _last_obj(class_):
            return max(
                (o.submit_date for o in class_.objects.filter(board=obj)),
                default=obj.pub_date,
            )

        return max([obj.pub_date, _last_obj(Evidence), _last_obj(Hypothesis)])
