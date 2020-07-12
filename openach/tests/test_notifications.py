from django.urls import reverse
from django.utils import timezone
from notifications.signals import notify

from openach.models import Board, BoardFollower, Evidence, Hypothesis
from openach.views.notifications import notify_add, notify_edit

from .common import PrimaryUserTestCase


class NotificationTests(PrimaryUserTestCase):
    """Basic tests for notifications."""

    def setUp(self):
        super().setUp()
        self.board = Board.objects.create(
            board_title="Board Title",
            board_desc="Description",
            creator=self.user,
            pub_date=timezone.now(),
        )
        BoardFollower.objects.create(
            board=self.board, user=self.user,
        )

    def test_public_cannot_get_notifications(self):
        """Test that users that are not logged in cannot access the notifications list."""
        response = self.client.get(reverse("openach:notifications"))
        self.assertEqual(response.status_code, 302)

    def test_can_view_empty_notifications(self):
        """Test that a logged in user can view an empty notifications list."""
        self.login()
        response = self.client.get(reverse("openach:notifications"))
        self.assertContains(response, "Notifications", status_code=200)

    def test_can_view_notifications(self):
        """Test that a logged in user can view one or more notifications."""
        notify.send(
            self.other, recipient=self.user, actor=self.other, verb="said hello!"
        )
        notify.send(
            self.other, recipient=self.user, actor=self.other, verb="said hello again!"
        )
        self.login()
        response = self.client.get(reverse("openach:notifications"))
        self.assertContains(response, "paul said hello!", status_code=200)
        self.assertContains(response, "paul said hello again!", status_code=200)

    def test_board_hypothesis_notifications(self):
        """Test the add/edit hypothesis notifications work render reasonably."""
        hypothesis = Hypothesis.objects.create(
            board=self.board, hypothesis_text="Hypothesis",
        )
        notify_add(self.board, self.other, hypothesis)
        notify_edit(self.board, self.other, hypothesis)
        self.login()
        response = self.client.get(reverse("openach:notifications"))
        self.assertContains(response, self.other.username, count=2)
        self.assertContains(response, self.board.board_title, count=2)
        self.assertContains(response, "edited hypothesis", count=1)
        self.assertContains(response, "added hypothesis", count=1)

    def test_board_evidence_notifications(self):
        """Test the add/edit evidence notifications work render reasonably."""
        evidence = Evidence.objects.create(board=self.board, evidence_desc="Evidence",)
        notify_add(self.board, self.other, evidence)
        notify_edit(self.board, self.other, evidence)
        self.login()
        response = self.client.get(reverse("openach:notifications"))
        self.assertContains(response, self.other.username, count=2)
        self.assertContains(response, self.board.board_title, count=2)
        self.assertContains(response, "edited evidence", count=1)
        self.assertContains(response, "added evidence", count=1)

    def test_can_clear_notifications(self):
        """Test that a user can clear notifications via POST request."""
        notify.send(
            self.other, recipient=self.user, actor=self.other, verb="said hello!"
        )
        notify.send(
            self.user, recipient=self.other, actor=self.user, verb="said hello!"
        )
        self.assertGreater(self.user.notifications.unread().count(), 0)
        self.login()
        response = self.client.post(
            reverse("openach:clear_notifications"), data={"clear": "clear",}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.notifications.unread().count(), 0)
        # make sure we didn't clear someone else's notifications
        self.assertGreater(self.other.notifications.unread().count(), 0)
