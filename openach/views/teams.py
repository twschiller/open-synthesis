

from collections import defaultdict
import itertools
import json
import logging
import random

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_http_methods, require_safe
from field_history.models import FieldHistory

from openach.models import Team, TeamRequest
from openach.decorators import cache_if_anon, cache_on_auth, account_required
from .util import make_paginator

from openach.forms import TeamCreateForm

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
            return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    else:
        form = TeamCreateForm()
    return render(request, 'teams/create_team.html', {'form': form})


def manage_team(request, team):

    return render(request, 'teams/manage_team.html', context={
        'team': team,
        'member_requests': TeamRequest.objects.filter(team=team, invitee__isnull=False)
    })

@login_required
@require_http_methods(['POST'])
@transaction.atomic
def decide_invitation(request, invite_id):
    invite = get_object_or_404(TeamRequest, pk=invite_id)

    if invite.team.owner != request.user:
        raise SuspiciousOperation(_('User is not the owner of the team'))

    if 'accept' in request.POST:
        invite.team.members.add(invite.invitee)
        invite.team.save()
        messages.success(request, _('Added {name} to the team').format(name=invite.invitee.username))
    elif 'reject' in request.POST:
        messages.success(request, _('Ignored {name}\'s team membership request').format(name=invite.invitee.username))
    else:
        return HttpResponseBadRequest()

    invite.delete()
    return HttpResponseRedirect(reverse('openach:view_team', args=(invite.team.id,)))


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def revoke_membership(request, team_id, member_id):
    team = get_object_or_404(Team, pk=team_id)
    user = get_object_or_404(User, pk=member_id)
    if team.owner != request.user:
        raise SuspiciousOperation(_('User is not the owner of the team'))
    elif user == team.owner:
        raise SuspiciousOperation(_('Cannot remove the owner from the team'))
    team.members.filter(id=member_id).delete()
    team.save()
    messages.success(request, _('Removed {name} from team').format(name=user.username))
    return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


@require_http_methods(['GET', 'POST'])
def view_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    if team.owner_id is not None and team.owner_id == request.user.id:
        return manage_team(request, team)

    is_member = team.members.filter(id=request.user.id).exists()

    if not is_member and not team.public:
        raise PermissionDenied()

    return render(request, 'teams/view_team.html', context={
        'team': team,
        'is_member': is_member,
        'pending_request': request.user.is_authenticated and TeamRequest.objects.filter(team_id=team, inviter__isnull=True, invitee=request.user).exists(),
        'pending_invitation': request.user.is_authenticated and TeamRequest.objects.filter(team_id=team, inviter__isnull=False, invitee=request.user).exists(),
    })


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def join_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    if team.members.filter(id=request.user.id).exists():
        raise SuspiciousOperation(_('User is already a member of the team'))
    elif TeamRequest.objects.filter(invitee=request.user, inviter__isnull=False, team=team).exists() or \
         not team.invitation_required:
        team.members.add(request.user)
        team.save()
        TeamRequest.objects.filter(invitee=request.user, team=team).delete()
        messages.success(request, _('Joined team {name}').format(name=team.name))
        return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))
    elif TeamRequest.objects.filter(invitee=request.user, team=team).exists():
        return HttpResponseBadRequest(_('User already has a membership request with the team'))
    else:
        TeamRequest.objects.create(invitee=request.user, team=team)
        messages.success(request, _('Requested invitation to team {name}').format(name=team.name))
        return HttpResponseRedirect(reverse('openach:view_team', args=(team.id,)))


@require_safe
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def team_listing(request):
    """Return a listing of public teams."""
    team_list = Team.objects.filter(public=True).order_by('name')
    desc = _('List of public teams on {name} and summary information').format(name=get_current_site(request).name)  # nopep8
    context = {
        'teams': make_paginator(request, team_list),
        'meta_description': desc,
    }
    return render(request, 'teams/teams.html', context)
