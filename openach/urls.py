"""Analysis of Competing Hypotheses Django Application URL Configuration.

See the Django documentation for more information:
* https://docs.djangoproject.com/en/2.1/ref/urls/
* https://docs.djangoproject.com/en/2.1/topics/http/urls/
"""
from django.urls import path

from . import views

# NOTE: Django's API doesn't follow constant naming convention for 'app_name' and 'urlpatterns'

app_name = "openach"  # pylint: disable=invalid-name

urlpatterns = [  # pylint: disable=invalid-name
    path("", views.site.index, name="index"),
    # NOTE: when running the dev server, Django will try to serve from the static file provider b/c of static prefix
    path("static/images/bitcoin.svg", views.site.bitcoin_qrcode, name="bitcoin_donate"),
    path("boards/", views.boards.board_listing, name="boards"),
    path(
        "accounts/<int:account_id>/boards/",
        views.boards.user_board_listing,
        name="user_boards",
    ),
    path(
        "accounts/notifications/clear/",
        views.notifications.clear_notifications,
        name="clear_notifications",
    ),
    path(
        "accounts/notifications/",
        views.notifications.notifications,
        name="notifications",
    ),
    path("teams/create/", views.teams.create_team, name="create_team"),
    path("teams/", views.teams.team_listing, name="teams"),
    path("teams/<int:team_id>/join/", views.teams.join_team, name="join_team"),
    path("teams/<int:team_id>/leave/", views.teams.leave_team, name="leave_team"),
    path("teams/<int:team_id>/", views.teams.view_team, name="view_team"),
    path("teams/<int:team_id>/edit/", views.teams.edit_team, name="edit_team"),
    path("teams/<int:team_id>/members/", views.teams.team_members, name="team_members"),
    path(
        "teams/<int:team_id>/members/invite/",
        views.teams.invite_members,
        name="invite_members",
    ),
    path(
        "teams/<int:team_id>/members/<int:member_id>/revoke/",
        views.teams.revoke_membership,
        name="revoke_membership",
    ),
    path(
        "teams/invitations/<int:invite_id>/",
        views.teams.decide_invitation,
        name="decide_invitation",
    ),
    path("boards/<int:board_id>/", views.boards.detail, name="detail"),
    path("boards/create/", views.boards.create_board, name="create_board"),
    path(
        "boards/<int:board_id>/history/",
        views.boards.board_history,
        name="board_history",
    ),
    path("boards/<int:board_id>/edit/", views.boards.edit_board, name="edit_board"),
    path(
        "boards/<int:board_id>/permissions/",
        views.boards.edit_permissions,
        name="edit_permissions",
    ),
    path(
        "boards/<int:board_id>/evidence/add/",
        views.evidence.add_evidence,
        name="add_evidence",
    ),
    path(
        "evidence/<int:evidence_id>/sources/add/",
        views.evidence.add_source,
        name="add_source",
    ),
    path(
        "evidence/<int:evidence_id>/sources/<int:source_id>/tag/",
        views.evidence.toggle_source_tag,
        name="tag_source",
    ),
    path(
        "evidence/<int:evidence_id>/edit/",
        views.evidence.edit_evidence,
        name="edit_evidence",
    ),
    path(
        "evidence/<int:evidence_id>/",
        views.evidence.evidence_detail,
        name="evidence_detail",
    ),
    path(
        "hypotheses/<int:hypothesis_id>/edit/",
        views.hypotheses.edit_hypothesis,
        name="edit_hypothesis",
    ),
    path(
        "boards/<int:board_id>/hypotheses/add/",
        views.hypotheses.add_hypothesis,
        name="add_hypothesis",
    ),
    path(
        "boards/<int:board_id>/evidence/<int:evidence_id>/evaluate/",
        views.boards.evaluate,
        name="evaluate",
    ),
    path(
        "boards/<int:board_id>/<slug:dummy_board_slug>/",
        views.boards.detail,
        name="detail_slug",
    ),
    path("about/", views.site.about, name="about"),
    # JSON API
    path("api/boards/", views.boards.board_search, name="board_search"),
    path("accounts/issue_invite/", views.profiles.issue_invite, name="issue_invite")
]
