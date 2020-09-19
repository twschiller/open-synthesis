import logging

from allauth.account.views import SignupView
from csp.decorators import csp_update
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.http import etag, require_safe

from openach.decorators import account_required, cache_if_anon, cache_on_auth
from openach.donate import bitcoin_donation_url, make_qr_code
from openach.models import Board, ProjectNews

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, "PAGE_CACHE_TIMEOUT_SECONDS", 60)
DEBUG = getattr(settings, "DEBUG", False)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def index(request):
    """Return a homepage view showing project information, news, and recent boards."""
    # Show all of the boards until we can implement tagging, search, etc.
    latest_board_list = Board.objects.user_readable(request.user)[:5]
    latest_project_news = ProjectNews.objects.filter(
        pub_date__lte=timezone.now()
    ).order_by("-pub_date")[:5]
    context = {
        "latest_board_list": latest_board_list,
        "latest_project_news": latest_project_news,
    }
    return render(request, "boards/index.html", context)


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def about(request):
    """Return an about view showing contribution, licensing, contact, and other information."""
    address = getattr(settings, "DONATE_BITCOIN_ADDRESS", None)
    context = {
        "bitcoin_address": address,
        "bitcoin_donate_url": bitcoin_donation_url(
            get_current_site(request).name, address
        ),
        "privacy_url": getattr(settings, "PRIVACY_URL", None),
    }
    return render(request, "boards/about.html", context=context)


@require_safe
def robots(request):
    """Return the robots.txt including the sitemap location (using the site domain) if the site is public."""
    private_instance = getattr(settings, "ACCOUNT_REQUIRED", False)
    context = {
        "sitemap": (
            "".join(
                [
                    "https://",
                    get_current_site(request).domain,
                    reverse("django.contrib.sitemaps.views.sitemap"),
                ]
            )
            if not private_instance
            else None
        ),
        "disallow_all": private_instance,
    }
    return render(request, "robots.txt", context, content_type="text/plain")


@require_safe
def certbot(dummy_request, challenge_key):  # pragma: no cover
    """Return a response to the Let's Encrypt Certbot challenge.

    If the challenge is not configured, raise a 404. For more information, please see:
        https://certbot.eff.org/
    """
    # ignore coverage since keys aren't available in the testing environment
    public_key = getattr(settings, "CERTBOT_PUBLIC_KEY")
    secret_key = getattr(settings, "CERTBOT_SECRET_KEY")
    if public_key and secret_key and public_key == challenge_key:
        return HttpResponse(secret_key)
    elif public_key and not secret_key:
        raise ImproperlyConfigured("CERTBOT_SECRET_KEY not set")
    else:
        raise Http404()


@require_safe
@etag(lambda r: getattr(settings, "DONATE_BITCOIN_ADDRESS", ""))
@cache_page(60 * 60)  # NOTE: if only etag is set, Django doesn't include cache headers
def bitcoin_qrcode(request):
    """Return a QR Code for donating via Bitcoin."""
    address = getattr(settings, "DONATE_BITCOIN_ADDRESS", None)
    if address:
        raw = make_qr_code(
            bitcoin_donation_url(get_current_site(request).name, address)
        )
        return HttpResponse(raw.getvalue(), content_type="image/svg+xml")
    else:
        raise Http404


@method_decorator(
    csp_update(
        # https://github.com/praekelt/django-recaptcha/issues/101
        # https://developers.google.com/recaptcha/docs/faq#im-using-content-security-policy-csp-on-my-website.-how-can-i-configure-it-to-work-with-recaptcha
        SCRIPT_SRC="'self' 'unsafe-inline' https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/",
        FRAME_SRC="'self' https://www.google.com/recaptcha/",
    ),
    name="dispatch",
)
class CaptchaSignupView(SignupView):
    pass
