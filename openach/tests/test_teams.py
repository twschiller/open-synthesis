from django.urls import reverse

from openach.forms import TeamCreateForm
from openach.models import Team, TeamRequest

from .common import HTTP_FORBIDDEN, HTTP_OK, HTTP_REDIRECT, PrimaryUserTestCase


class TeamTests(PrimaryUserTestCase):
    def test_view_team(self):
        """Smoke test for team detail page."""
        team = Team.objects.create(name="Public Team")
        response = self.client.get(reverse("openach:view_team", args=(team.id,)))
        self.assertStatus(response, HTTP_OK)

    def test_view_private_team(self):
        """Test that only team-members can view a private team page."""
        team = Team.objects.create(name="Private Team", public=False)

        response = self.client.get(reverse("openach:view_team", args=(team.id,)))
        self.assertStatus(response, HTTP_FORBIDDEN)

        self.login()

        response = self.client.get(reverse("openach:view_team", args=(team.id,)))
        self.assertStatus(response, HTTP_FORBIDDEN)

        team.members.add(self.user)
        team.save()

        response = self.client.get(reverse("openach:view_team", args=(team.id,)))
        self.assertStatus(response, HTTP_OK)

    def test_view_manage_team(self):
        """Test that the team owner sees the team management view."""
        self.team = Team.objects.create(name="Team", owner=self.user)
        self.login()

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertTemplateUsed(response, "teams/manage_team.html")

    def test_view_create_team_page(self):
        """Test that a logged-in user can view the create team page."""
        response = self.client.get(reverse("openach:create_team"))
        self.assertStatus(response, HTTP_REDIRECT)  # redirect to login page

        self.login()

        response = self.client.get(reverse("openach:create_team"))
        self.assertContains(response, "Create Team")

    def test_create_team_form(self):
        """Smoke test for create team form."""
        form = TeamCreateForm(
            {
                "name": "New team",
                "description": "New team description",
                "url": None,
                "public": True,
                "invitation_required": False,
            }
        )
        self.assertTrue(form.is_valid())

    def test_edit_team(self):
        """Test that a team owner can edit a team's details."""
        self.team = Team.objects.create(name="Team", owner=self.user)

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertNotContains(response, "Edit Details")

        self.login()

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertContains(response, "Edit Details")

        response = self.client.get(reverse("openach:edit_team", args=(self.team.id,)))
        self.assertContains(response, "Edit Team")

        desc = "New team description"
        response = self.client.post(
            reverse("openach:edit_team", args=(self.team.id,)),
            data={"name": "Team", "description": desc, "public": False,},
        )
        self.assertEqual(response.status_code, HTTP_REDIRECT)  # succeeded

        self.team.refresh_from_db()
        self.assertEqual(self.team.description, desc)

    def test_can_create_team_post(self):
        """Test that a user can create a team via a POST request."""
        self.login()
        team_name = "Test Team"
        team_description = "A test team"
        response = self.client.post(
            reverse("openach:create_team"),
            data={"name": team_name, "description": team_description, "public": True,},
        )
        self.assertEqual(response.status_code, HTTP_REDIRECT)  # succeeded

        self.assertEqual(Team.objects.count(), 1)
        team = Team.objects.get(name=team_name)
        self.assertEqual(team.description, team_description)

        self.assertTrue(team.members.filter(id=self.user.id).exists())


class TeamMembership(PrimaryUserTestCase):
    def test_user_can_join_directly(self):
        """Test that user can join/leave from team page if invitation is not required."""
        self.team = Team.objects.create(name="Test Team", invitation_required=False)

        self.login()

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertContains(response, "Join Team")

        response = self.client.post(reverse("openach:join_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_REDIRECT)

        # no request is generated if the user just joins the team
        self.assertFalse(
            TeamRequest.objects.filter(invitee=self.user, team=self.team).exists()
        )

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertContains(response, "Leave Team")

        response = self.client.post(reverse("openach:leave_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_REDIRECT)

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertContains(response, "Join Team")

    def test_user_can_request_invite(self):
        """Test that user can request invite from the team page."""
        self.team = Team.objects.create(
            name="Test Team", owner=self.other, invitation_required=True
        )

        self.login()

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertContains(response, "Request Membership")

        response = self.client.post(reverse("openach:join_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_REDIRECT)

        self.assertEqual(self.other.notifications.unread().count(), 1)

        self.assertTrue(
            TeamRequest.objects.filter(invitee=self.user, team=self.team).exists()
        )

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_OK)
        self.assertContains(response, "Membership Pending")

    def test_user_can_accept_invitation(self):
        """Test that a user can accept a team invite from the team page."""

        self.team = Team.objects.create(name="Test Team", invitation_required=True)
        TeamRequest.objects.create(
            inviter=self.other, invitee=self.user, team=self.team
        )

        self.login()

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertContains(response, "Accept Invitation")

        response = self.client.post(reverse("openach:join_team", args=(self.team.id,)))
        self.assertStatus(response, HTTP_REDIRECT)

        response = self.client.get(reverse("openach:view_team", args=(self.team.id,)))
        self.assertContains(response, "Leave Team")

    def test_can_revoke_membership(self):
        """Test that an owner can revoke membership for teams with invitations."""

        self.team = Team.objects.create(
            name="Test Team", invitation_required=True, owner=self.user
        )
        self.team.members.add(self.other)
        self.team.save()

        self.login()

        response = self.client.post(
            reverse("openach:revoke_membership", args=(self.team.id, self.other.id))
        )
        self.assertStatus(response, HTTP_REDIRECT)

        self.assertFalse(self.team.members.filter(id=self.other.id).exists())

        self.logout()

        self.assertEqual(self.other.notifications.unread().count(), 1)

    def test_can_accept_membership_request(self):
        """Test that an owner can accept a membership request."""

        self.team = Team.objects.create(
            name="Test Team", invitation_required=True, owner=self.user
        )

        self.login()

        membership_request = TeamRequest.objects.create(
            invitee=self.other, team=self.team
        )

        response = self.client.post(
            reverse("openach:decide_invitation", args=(membership_request.id,)),
            data={"accept": True,},
        )
        self.assertStatus(response, HTTP_REDIRECT)

        self.assertTrue(self.team.members.filter(id=self.other.id).exists())
        self.assertFalse(TeamRequest.objects.filter(invitee=self.other).exists())

        self.assertEqual(self.other.notifications.unread().count(), 1)

    def test_can_reject_membership_request(self):
        """Test that an owner can reject a membership request."""

        self.team = Team.objects.create(
            name="Test Team", invitation_required=True, owner=self.user
        )

        self.login()

        membership_request = TeamRequest.objects.create(
            invitee=self.other, team=self.team
        )

        response = self.client.post(
            reverse("openach:decide_invitation", args=(membership_request.id,)),
            data={"reject": True,},
        )
        self.assertStatus(response, HTTP_REDIRECT)

        self.assertFalse(self.team.members.filter(id=self.other.id).exists())
        self.assertFalse(TeamRequest.objects.filter(invitee=self.other).exists())

        self.assertEqual(self.other.notifications.unread().count(), 1)

    def test_can_invite_members(self):
        """Test that an owner can invite members to a team."""

        self.team = Team.objects.create(
            name="Test Team", invitation_required=True, owner=self.user
        )

        self.login()

        response = self.client.get(
            reverse("openach:invite_members", args=(self.team.id,))
        )
        self.assertTemplateUsed(response, "teams/invite.html")

        response = self.client.post(
            reverse("openach:invite_members", args=(self.team.id,)),
            data={"members": [self.other.id],},
        )
        self.assertStatus(response, HTTP_REDIRECT)
        self.assertEqual(
            TeamRequest.objects.filter(
                inviter=self.user, invitee=self.other, team=self.team
            ).count(),
            1,
        )


class TeamListingTests(PrimaryUserTestCase):
    def test_team_listing(self):
        """List should include all public teams, including invite-only."""
        Team.objects.create(name="Public Team", public=True)
        Team.objects.create(name="Member Team", public=True, invitation_required=True)

        response = self.client.get(reverse("openach:teams"))
        self.assertContains(response, "Public Team")
        self.assertContains(response, "Member Team")

    def test_hide_private_teams(self):
        """Hide private teams from the team listing."""
        Team.objects.create(name="Public Team", public=True)
        team = Team.objects.create(name="Private Team", public=False)

        response = self.client.get(reverse("openach:teams"))
        self.assertStatus(response, HTTP_OK)

        self.login()

        # don't show because user is not a member
        response = self.client.get(reverse("openach:teams"))
        self.assertNotContains(response, "Private Team")

        team.members.add(self.user)
        team.save()

        # show because user is now a member
        response = self.client.get(reverse("openach:teams"))
        self.assertContains(response, "Private Team")
