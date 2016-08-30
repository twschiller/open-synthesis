from django.contrib.sitemaps import Sitemap
from .models import Board, Evidence, Hypothesis

# https://docs.djangoproject.com/en/1.10/ref/contrib/sitemaps


class BoardSitemap(Sitemap):
    protocol = "https"
    changefreq = "daily"
    priority = 0.5

    def items(self):
        return Board.objects.filter()

    def lastmod(self, obj):
        """
        Returns the last time the board or its content was modified. Currently returns the last time the board was
        structurally modified, that is a hypothesis or piece of evidence was added.
        """
        def last_obj(class_): return max(
            map(lambda x: x.submit_date, class_.objects.filter(board=obj)),
            default=obj.pub_date)
        return max([obj.pub_date, last_obj(Evidence), last_obj(Hypothesis)])
