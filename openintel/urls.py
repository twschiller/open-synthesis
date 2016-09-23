"""Open Synthesis URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import TemplateView
from django.contrib.sitemaps.views import sitemap
from django.conf import settings
from openach import views
from openach.sitemap import BoardSitemap
import notifications.urls


ACCOUNT_REQUIRED = getattr(settings, 'ACCOUNT_REQUIRED', False)

# NOTE: Django's API doesn't follow constant naming convention for 'sitemaps' and 'urlpatterns'

# https://docs.djangoproject.com/en/1.10/ref/contrib/sitemaps/#initialization
sitemaps = {  # pylint: disable=invalid-name
    'board': BoardSitemap,
}

urlpatterns = [  # pylint: disable=invalid-name
    url(r'^admin/', admin.site.urls),
    url(r'robots\.txt', views.robots, name='robots'),
    url(r'contribute\.json', TemplateView.as_view(template_name='contribute.json', content_type='application/json')),
    url(r'^accounts/(?P<account_id>[0-9]+)/$', views.profile, name='profile'),
    url(r'^accounts/profile/', views.private_profile, name='private_profile'),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^comments/', include('django_comments.urls')),
    url('^inbox/notifications/', include(notifications.urls, namespace='notifications')),
    url(r'^invitations/', include('invitations.urls', namespace='invitations')),
    url(r'', include('openach.urls')),
    url(r'\.well-known/acme-challenge/(?P<challenge_key>[a-zA-Z0-9\-]+)$', views.certbot),
]

if not ACCOUNT_REQUIRED:  # pylint: disable=invalid-name
    # Only allow clients to view the sitemap if the admin is running a public instance
    urlpatterns.insert(0, url(r'^sitemap\.xml$', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'))  # nopep8
