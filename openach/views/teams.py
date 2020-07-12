from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction
from django.db.models.functions import Lower
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe
from notifications.signals import notify

from openach.models import Team, TeamRequest
from openach.decorators import account_required, cache_if_anon
from .util import make_paginator

from openach.forms import TeamCreateForm, TeamInviteForm

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, 'PAGE_CACHE_TIMEOUT_SECONDS', 60)

@require_http_methods(['GET', 'POST'])
@login_required
def create_team(request):
    """Return a team creation view, or handle the form submission."""
    if request.method == 'POST':
        form = TeamCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                team = form.save(commit=False)
                team.owner = request.user
                team.creator = request.user
                team.save()
                team.members.add(request.user)
                team.save()
            return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    else:
        form = TeamCreateForm()
    return render(request, 'teams/create_team.html', {'form': form})


@require_http_methods(['GET', 'POST'])
@login_required
def edit_team(request, team_id):
    """Return a team edit view, or handle the form submission."""
    # TODO: if user turns off invitation-required, let everyone in who had outstanding membership requests

    team = get_object_or_404(Team, pk=team_id)

    if team.owner_id is None or team.owner_id != request.user.id:
        raise SuspiciousOperation(_('User is not the owner of the team'))

    if request.method == 'POST':
        form = TeamCreateForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, _('Updated team information'))
            return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    else:
        form = TeamCreateForm(instance=team)
    return render(request, 'teams/edit_team.html', context={
        'team': team,
        'form': form
    })


@require_http_methods(['GET', 'POST'])
@login_required
def invite_members(request, team_id):
    """Return a team edit view, or handle the form submission."""
    team = get_object_or_404(Team, pk=team_id)

    if team.owner_id is None or team.owner_id != request.user.id:
        raise SuspiciousOperation(_('User is not the owner of the team'))

    if request.method == 'POST':
        form = TeamInviteForm(request.POST, team=team)
        if form.is_valid():
            to_invite = form.cleaned_data['members']
            invites = [TeamRequest(team=team, inviter=request.user, invitee=x) for x in to_invite]
            TeamRequest.objects.bulk_create(invites)
            for user in to_invite:
                notify.send(request.user, recipient=user, actor=request.user, verb='invite', action_object=team, target=user)
            messages.success(request, _('Invited {count} members to the team').format(count=len(to_invite)))
            return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    else:
        form = TeamInviteForm(team=team)
    return render(request, 'teams/invite.html', context={
        'team': team,
        'form': form
    })


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def decide_invitation(request, invite_id):
    invite = get_object_or_404(TeamRequest, pk=invite_id)
    team = invite.team

    if team.owner_id is None or team.owner_id != request.user.id:
        raise SuspiciousOperation(_('User is not the owner of the team'))
    elif 'accept' in request.POST:
        invite.team.members.add(invite.invitee)
        invite.team.save()
        notify.send(request.user, recipient=invite.invitee, actor=request.user, verb='accept', action_object=team, target=invite.invitee)
        messages.success(request, _('Added {name} to the team').format(name=invite.invitee.username))
    elif 'reject' in request.POST:
        notify.send(request.user, recipient=invite.invitee, actor=request.user, verb='reject', action_object=team, target=invite.invitee)
        messages.success(request, _('Ignored {name}\'s team membership request').format(name=invite.invitee.username))
    else:
        return HttpResponseBadRequest(_('POST request must include either "{accept}" or "{reject}"').format(accept='accept', reject='reject'))

    invite.delete()
    return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def revoke_membership(request, team_id, member_id):
    team = get_object_or_404(Team, pk=team_id)
    user = get_object_or_404(User, pk=member_id)

    if team.owner_id is None or team.owner_id != request.user.id:
        raise SuspiciousOperation(_('User is not the owner of the team'))
    elif user == team.owner:
        raise SuspiciousOperation(_('Cannot remove the owner from the team'))
    elif not team.invitation_required:
        raise SuspiciousOperation(_('Cannot remove user from teams that don\'t require an invitation'))

    team.members.remove(user)
    team.save()
    notify.send(request.user, recipient=user, actor=request.user, verb='remove', action_object=team, target=user)
    messages.success(request, _('Removed {name} from team').format(name=user.username))
    return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


def manage_team(request, team):
    return render(request, 'teams/manage_team.html', context={
        'team': team,
        'member_requests': TeamRequest.objects.filter(team=team, inviter__isnull=True)
    })


def member_status(user, team):
    is_member = team.members.filter(id=user.id).exists()
    pending_invitation = user.is_authenticated and TeamRequest.objects.filter(team_id=team, inviter__isnull=False, invitee=user).exists()
    return is_member, pending_invitation


@require_http_methods(['GET', 'POST'])
@account_required
def view_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    if team.owner_id is not None and team.owner_id == request.user.id:
        return manage_team(request, team)

    is_member, pending_invitation = member_status(request.user, team)

    if not is_member and not team.public and not pending_invitation:
        raise PermissionDenied()

    return render(request, 'teams/view_team.html', context={
        'team': team,
        'is_member': is_member,
        'pending_request': request.user.is_authenticated and TeamRequest.objects.filter(team_id=team, inviter__isnull=True, invitee=request.user).exists(),
        'pending_invitation': pending_invitation,
    })


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def join_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    if team.members.filter(id=request.user.id).exists():
        raise SuspiciousOperation(_('User is already a member of the team'))
    elif TeamRequest.objects.filter(invitee=request.user, inviter__isnull=False, team=team).exists() or not team.invitation_required:
        team.members.add(request.user)
        team.save()
        TeamRequest.objects.filter(invitee=request.user, team=team).delete()
        messages.success(request, _('Joined team {name}').format(name=team.name))
        return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    elif TeamRequest.objects.filter(invitee=request.user, team=team).exists():
        return HttpResponseBadRequest(_('User already has a membership request with the team'))
    else:
        TeamRequest.objects.create(invitee=request.user, team=team)
        if team.owner:
            notify.send(request.user, recipient=team.owner, actor=request.user, verb='request_membership', target=team)
        messages.success(request, _('Requested invitation to team {name}').format(name=team.name))
        return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def leave_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    if not team.members.filter(id=request.user.id).exists():
        raise SuspiciousOperation(_('User is not a member of the team'))
    else:
        team.members.remove(request.user)
        team.save()
        messages.success(request, _('Left team {name}').format(name=team.name))
        return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


@require_safe
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
@account_required
def team_listing(request):
    """Return a listing of teams visible to the user."""
    team_list = Team.objects.user_visible(request.user).order_by(Lower('name'))
    desc = _('List of teams on {name} and summary information').format(name=get_current_site(request).name)  # nopep8

    user_teams = set()
    user_invites = set()
    user_pending = set()
    user_owns = set()

    if request.user.is_authenticated:
        user_invites = set(TeamRequest.objects.filter(invitee=request.user, inviter__isnull=False).values_list('team', flat=True))
        user_pending = set(TeamRequest.objects.filter(invitee=request.user, inviter__isnull=True).values_list('team', flat=True))
        user_teams = set(request.user.team_set.values_list('id', flat=True))
        user_owns = set(Team.objects.filter(owner=request.user).values_list('id', flat=True))

    return render(request, 'teams/teams.html', {
        'teams': make_paginator(request, team_list),
        'meta_description': desc,
        'user_teams': user_teams,
        'user_invites': user_invites,
        'user_pending': user_pending,
        'user_owns': user_owns,
    })


@require_safe
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
@account_required
def team_members(request, team_id):
    """Return a listing of members for the given team."""
    team = get_object_or_404(Team, pk=team_id)

    is_member, pending_invitation = member_status(request.user, team)

    if not is_member and not team.public and not pending_invitation:
        raise PermissionDenied()

    return render(request, 'teams/members.html', {
        'team': team,
        'members': make_paginator(request, team.members.order_by(Lower('username'))),
        'is_owner': team.owner == request.user,
    })
