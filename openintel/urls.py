"""Open Synthesis URL Configuration.

See the Django documentation for more information:
* https://docs.djangoproject.com/en/2.1/ref/urls/
* https://docs.djangoproject.com/en/2.1/topics/http/urls/
"""
import notifications.urls
from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from openach import views
from openach.sitemap import BoardSitemap

ACCOUNT_REQUIRED = getattr(settings, "ACCOUNT_REQUIRED", False)

# NOTE: Django's API doesn't follow constant naming convention for 'sitemaps' and 'urlpatterns'

# https://docs.djangoproject.com/en/1.10/ref/contrib/sitemaps/#initialization
sitemaps = {  # pylint: disable=invalid-name
    "board": BoardSitemap,
}

urlpatterns = [  # pylint: disable=invalid-name
    path("admin/", admin.site.urls),
    path("robots.txt", views.site.robots, name="robots"),
    path(
        "contribute.json",
        TemplateView.as_view(
            template_name="contribute.json", content_type="application/json"
        ),
    ),
    path(
        "accounts/signup/",
        views.site.CaptchaSignupView.as_view(),
        name="account_signup",
    ),
    path("accounts/<int:account_id>/", views.profiles.profile, name="profile"),
    path("accounts/profile/", views.profiles.private_profile, name="private_profile"),
    path("accounts/", include("allauth.urls")),
    path("comments/", include("django_comments.urls")),
    path(
        "inbox/notifications/", include(notifications.urls, namespace="notifications")
    ),
    path("invitations/", include("invitations.urls", namespace="invitations")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("openach.urls")),
    re_path(
        r"\.well-known/acme-challenge/(?P<challenge_key>[a-zA-Z0-9\-_]+)$",
        views.site.certbot,
    ),
]


if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls)),] + urlpatterns


if not ACCOUNT_REQUIRED:  # pylint: disable=invalid-name
    # Only allow clients to view the sitemap if the admin is running a public instance
    urlpatterns.insert(
        0,
        path(
            r"sitemap.xml",
            sitemap,
            {"sitemaps": sitemaps},
            name="django.contrib.sitemaps.views.sitemap",
        ),
    )  # nopep8
