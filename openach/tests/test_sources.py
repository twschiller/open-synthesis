from django.urls import reverse

from openach.forms import EvidenceSourceForm
from openach.models import URL_MAX_LENGTH, Evidence, EvidenceSource

from .common import PrimaryUserTestCase, create_board


class AddSourceTests(PrimaryUserTestCase):
    def setUp(self):
        super().setUp()
        self.board = create_board("Test Board", days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
        )

    def test_require_login_for_add_source(self):
        """Test that the user must be logged in to access the add source form."""
        response = self.client.get(
            reverse("openach:add_source", args=(self.evidence.id,))
        )
        self.assertEqual(response.status_code, 302)

    def test_add_source_show_form(self):
        """Test that the add evidence form renders in a reasonable way."""
        self.login()
        response = self.client.get(
            reverse("openach:add_source", args=(self.evidence.id,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "boards/add_source.html")

        # the view should display the evidence description
        self.assertContains(response, self.evidence.evidence_desc)
        self.assertContains(response, "Add Corroborating Source")
        self.assertContains(response, "Return to Evidence")

    def test_add_evidence_source_submit(self):
        """Test that the source is actually added to the database when the user submits the form."""
        self.login()
        url = "https://google.com"

        for corroborating in [True, False]:
            response = self.client.post(
                reverse("openach:add_source", args=(self.evidence.id,)),
                data={
                    "source_url": url,
                    "source_date": "1/1/2016",
                    "corroborating": str(corroborating),
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertGreater(len(EvidenceSource.objects.filter(source_url=url)), 0)
            self.assertGreater(
                len(EvidenceSource.objects.filter(corroborating=corroborating)), 0
            )

    def test_add_conflicting_evidence_form(self):
        """Test that the form is for conflicting sources when ?kind=conflicting query parameter is supplied."""
        self.login()
        response = self.client.get(
            reverse("openach:add_source", args=(self.evidence.id,))
            + "?kind=conflicting"
        )
        self.assertContains(response, "Add Conflicting Source")

    def test_retain_source_type_on_form_error(self):
        """Test that the form is for conflicting sources when user submits a invalid form without a query string."""
        self.login()
        url = "https://google.com"
        response = self.client.post(
            reverse("openach:add_source", args=(self.evidence.id,)),
            data={
                # intentionally leave off the evidence_date
                "source_url": url,
                "corroborating": False,
            },
        )
        self.assertContains(response, "Add Conflicting Source", status_code=200)

    def test_reject_long_url(self):
        """Test the the add source form rejects long URLs (issue #58)."""
        form = EvidenceSourceForm(
            {
                "source_url": "https://google.com" + ("x" * URL_MAX_LENGTH),
                "source_date": "1/1/2016",
            }
        )
        self.assertFalse(form.is_valid())

    def test_add_conflicting_evidence_source_form(self):
        """Test that the form validation passes for reasonable input."""
        form = EvidenceSourceForm(
            {
                "source_url": "https://google.com",
                "source_date": "1/1/2016",
                "corroborating": "False",
            }
        )
        self.assertTrue(form.is_valid())
        form = EvidenceSourceForm(
            {
                "source_url": "https://google.com",
                "source_date": "1/1/2016",
                "corroborating": "True",
            }
        )
        self.assertTrue(form.is_valid())

    def test_add_conflicting_evidence_source(self):
        """Test that a conflicting source can be added via the form."""
        self.login()
        response = self.client.post(
            reverse("openach:add_source", args=(self.evidence.id,)),
            data={
                "source_url": "https://google.com",
                "source_date": "1/1/2016",
                "corroborating": "False",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(EvidenceSource.objects.filter(corroborating=False)), 0)
        self.assertEqual(len(EvidenceSource.objects.filter(corroborating=True)), 0)
