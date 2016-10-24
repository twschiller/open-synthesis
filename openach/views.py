"""Analysis of Competing Hypotheses Django Application Views Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/topics/http/views/
"""
from collections import defaultdict
import itertools
import logging
import random
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404
# NOTE: django.core.urlresolvers was deprecated in Django 1.10. Landscape is loading version 1.9.9 for some reason
from django.urls import reverse  # pylint: disable=no-name-in-module
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods, require_safe, etag
from field_history.models import FieldHistory
from notifications.signals import notify

from .auth import check_edit_authorization
from .decorators import cache_if_anon, cache_on_auth, account_required
from .donate import bitcoin_donation_url, make_qr_code
from .forms import BoardCreateForm, BoardForm, EvidenceForm, EvidenceSourceForm, SettingsForm, HypothesisForm
from .forms import BoardPermissionForm
from .metrics import aggregate_vote, hypothesis_sort_key, evidence_sort_key, calc_disagreement
from .metrics import generate_contributor_count, generate_evaluator_count
from .metrics import user_boards_contributed, user_boards_created, user_boards_evaluated
from .models import Board, Hypothesis, Evidence, EvidenceSource, Evaluation, Eval, AnalystSourceTag, EvidenceSourceTag
from .models import ProjectNews, BoardFollower, BoardPermissions
from .tasks import fetch_source_metadata

# XXX: allow_remove logic should probably be refactored to a template context processor

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

PAGE_CACHE_TIMEOUT_SECONDS = 60
DEBUG = getattr(settings, 'DEBUG', False)
BOARD_SEARCH_RESULTS_MAX = 5


def _remove_and_redirect(request, removable, message_detail):
    """Mark a model as removed and redirect the user to the associated board detail page."""
    if getattr(settings, 'EDIT_REMOVE_ENABLED', True):
        removable.removed = True
        removable.save()
        class_name = removable._meta.verbose_name.title()  # pylint: disable=protected-access
        class_ = class_name[:1].lower() + class_name[1:] if class_name else ''
        messages.success(request, _('Removed {object_type}: {detail}').format(object_type=class_, detail=message_detail))  # nopep8
        return HttpResponseRedirect(reverse('openach:detail', args=(removable.board.id,)))
    else:
        raise PermissionDenied()


def make_paginator(request, object_list, per_page=10, orphans=3):
    """Return a paginator for object_list from request."""
    paginator = Paginator(object_list, per_page=per_page, orphans=orphans)
    page = request.GET.get('page')
    try:
        objects = paginator.page(page)
    except PageNotAnInteger:
        # if page is not an integer, deliver first page.
        objects = paginator.page(1)
    except EmptyPage:
        # if page is out of range (e.g. 9999), deliver last page of results.
        objects = paginator.page(paginator.num_pages)
    return objects


def notify_followers(board, actor, verb, action_object):
    """Notify board followers of that have read permissions for the board."""
    for follow in board.followers.all().select_related('user'):
        if follow.user != actor and board.can_read(follow.user):
            notify.send(actor, recipient=follow.user, actor=actor, verb=verb,
                        action_object=action_object, target=board)


def notify_add(board, actor, action_object):
    """Notify board followers of an addition."""
    notify_followers(board, actor, 'added', action_object)


def notify_edit(board, actor, action_object):
    """Notify board followers of an edit."""
    notify_followers(board, actor, 'edited', action_object)


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def index(request):
    """Return a homepage view showing project information, news, and recent boards."""
    # Show all of the boards until we can implement tagging, search, etc.
    latest_board_list = Board.objects.user_readable(request.user)[:5]
    latest_project_news = ProjectNews.objects.filter(pub_date__lte=timezone.now()).order_by('-pub_date')[:5]
    context = {
        'latest_board_list': latest_board_list,
        'latest_project_news': latest_project_news,
    }
    return render(request, 'boards/index.html', context)


@require_safe
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def board_listing(request):
    """Return a paginated board listing view showing all boards and their popularity."""
    board_list = Board.objects.user_readable(request.user).order_by('-pub_date')
    metric_timeout_seconds = 60 * 2
    desc = _('List of intelligence boards on {name} and summary information').format(name=get_current_site(request).name)  # nopep8
    context = {
        'boards': make_paginator(request, board_list),
        'contributors': cache.get_or_set('contributor_count', generate_contributor_count(), metric_timeout_seconds),
        'evaluators': cache.get_or_set('evaluator_count', generate_evaluator_count(), metric_timeout_seconds),
        'meta_description': desc,
    }
    return render(request, 'boards/boards.html', context)


@require_safe
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def user_board_listing(request, account_id):
    """Return a paginated board listing view for account with account_id."""
    metric_timeout_seconds = 60 * 2

    queries = {
        # default to boards contributed to
        None: lambda x: ('contributed to', user_boards_contributed(x, viewing_user=request.user)),
        'created': lambda x: ('created', user_boards_created(x, viewing_user=request.user)),
        'evaluated': lambda x: ('evaluated', user_boards_evaluated(x, viewing_user=request.user)),
        'contribute': lambda x: ('contributed to', user_boards_contributed(x, viewing_user=request.user)),
    }

    user = get_object_or_404(User, pk=account_id)
    query = request.GET.get('query')
    verb, board_list = queries.get(query, queries[None])(user)
    desc = _('List of intelligence boards user {username} has {verb}').format(username=user.username, verb=verb)
    context = {
        'user': user,
        'boards': make_paginator(request, board_list),
        'contributors': cache.get_or_set('contributor_count', generate_contributor_count(), metric_timeout_seconds),
        'evaluators': cache.get_or_set('evaluator_count', generate_evaluator_count(), metric_timeout_seconds),
        'meta_description': desc,
        'verb': verb
    }
    return render(request, 'boards/user_boards.html', context)


@require_safe
@login_required
def notifications(request):
    """Return a paginated list of notifications for the user."""
    notification_list = request.user.notifications.unread()
    context = {
        'notifications': make_paginator(request, notification_list),
    }
    return render(request, 'boards/notifications/notifications.html', context)


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def about(request):
    """Return an about view showing contribution, licensing, contact, and other information."""
    address = getattr(settings, 'DONATE_BITCOIN_ADDRESS', None)
    context = {
        'bitcoin_address': address,
        'bitcoin_donate_url': bitcoin_donation_url(get_current_site(request).name, address),
        'privacy_url': getattr(settings, 'PRIVACY_URL', None),
    }
    return render(request, 'boards/about.html', context=context)


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def detail(request, board_id, dummy_board_slug=None):
    """Return a detail view for the given board.

    Evidence is sorted in order of diagnosticity. Hypotheses are sorted in order of consistency.
    """
    # NOTE: Django's page cache considers full URL including dummy_board_slug. In the future, we may want to adjust
    # the page key to only consider the id and the query parameters.
    # https://docs.djangoproject.com/en/1.10/topics/cache/#the-per-view-cache
    # NOTE: cannot cache page for logged in users b/c comments section contains CSRF and other protection mechanisms.
    view_type = 'aggregate' if request.GET.get('view_type') is None else request.GET['view_type']

    board = get_object_or_404(Board, pk=board_id)
    permissions = board.permissions.for_user(request.user)

    if 'read_board' not in permissions:
        raise PermissionDenied()

    vote_type = request.GET.get('vote_type', default=(
        'collab'
        # rewrite to avoid unnecessary lookup if key is present?
        if board.permissions.collaborators.filter(pk=request.user.id).exists()
        else 'all'
    ))

    all_votes = list(board.evaluation_set.select_related('user'))

    # calculate aggregate and disagreement for each evidence/hypothesis pair
    agg_votes = all_votes
    if vote_type == 'collab':
        collaborators = set([c.id for c in board.permissions.collaborators.all()])
        agg_votes = [v for v in all_votes if v.user_id in collaborators]

    def _pair_key(evaluation):
        return evaluation.evidence_id, evaluation.hypothesis_id
    keyed = defaultdict(list)
    for vote in agg_votes:
        keyed[_pair_key(vote)].append(Eval(vote.value))
    aggregate = {k: aggregate_vote(v) for k, v in keyed.items()}
    disagreement = {k: calc_disagreement(v) for k, v in keyed.items()}

    user_votes = (
        {_pair_key(v): Eval(v.value) for v in all_votes if v.user_id == request.user.id}
        if request.user.is_authenticated
        else None
    )

    # augment hypotheses and evidence with diagnosticity and consistency
    def _group(first, second, func, key):
        return [(f, func([keyed[key(f, s)] for s in second])) for f in first]
    hypotheses = list(board.hypothesis_set.filter(removed=False))
    evidence = list(board.evidence_set.filter(removed=False))
    hypothesis_consistency = _group(hypotheses, evidence, hypothesis_sort_key, key=lambda h, e: (e.id, h.id))
    evidence_diagnosticity = _group(evidence, hypotheses, evidence_sort_key, key=lambda e, h: (e.id, h.id))

    context = {
        'board': board,
        'permissions': permissions,
        'evidences': sorted(evidence_diagnosticity, key=lambda e: e[1]),
        'hypotheses': sorted(hypothesis_consistency, key=lambda h: h[1]),
        'view_type': view_type,
        'vote_type': vote_type,
        'votes': aggregate,
        'user_votes': user_votes,
        'disagreement': disagreement,
        'meta_description': board.board_desc,
        'allow_share': not getattr(settings, 'ACCOUNT_REQUIRED', False),
        'debug_stats': DEBUG,
    }
    return render(request, 'boards/detail.html', context)


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def board_history(request, board_id):
    """Return a view with the modification history (board details, evidence, hypotheses) for the board."""
    # this approach to grabbing the history will likely be too slow for big boards
    def _get_history(models):
        changes = [FieldHistory.objects.get_for_model(x).select_related('user') for x in models]
        return itertools.chain(*changes)

    board = get_object_or_404(Board, pk=board_id)

    if 'read_board' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    history = [
        _get_history([board]),
        _get_history(Evidence.all_objects.filter(board=board)),
        _get_history(Hypothesis.all_objects.filter(board=board)),
    ]
    history = list(itertools.chain(*history))
    history.sort(key=lambda x: x.date_created, reverse=True)
    return render(request, 'boards/board_audit.html', {'board': board, 'history': history})


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def create_board(request):
    """Return a board creation view, or handle the form submission.

    Set default permissions for the new board. Mark board creator as a board follower.
    """
    if request.method == 'POST':
        form = BoardCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                board = form.save(commit=False)
                board.creator = request.user
                board.pub_date = timezone.now()
                board.save()
                BoardPermissions.objects.create(board=board)
                for hypothesis_key in ['hypothesis1', 'hypothesis2']:
                    Hypothesis.objects.create(
                        board=board,
                        hypothesis_text=form.cleaned_data[hypothesis_key]
                    )
                BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                    'is_creator': True,
                })

            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardCreateForm()
    return render(request, 'boards/create_board.html', {'form': form})


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_board(request, board_id):
    """Return a board edit view, or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)
    check_edit_authorization(request, board)
    allow_remove = request.user.is_staff and getattr(settings, 'EDIT_REMOVE_ENABLED', True)

    if request.method == 'POST':
        form = BoardForm(request.POST, instance=board)
        if 'remove' in form.data:
            if allow_remove:
                board.removed = True
                board.save()
                messages.success(request, _('Removed board {name}').format(name=board.board_title))
                return HttpResponseRedirect(reverse('openach:index'))
            else:
                raise PermissionDenied()

        elif form.is_valid():
            form.save()
            messages.success(request, _('Updated board title and/or description.'))
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardForm(instance=board)

    context = {
        'form': form,
        'board': board,
        'allow_remove': allow_remove
    }

    return render(request, 'boards/edit_board.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_permissions(request, board_id):
    """View board permissions form and handle form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if not (request.user.is_staff or request.user.id == board.creator_id):
        raise PermissionDenied()

    if request.method == 'POST':
        form = BoardPermissionForm(request.POST, instance=board.permissions)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardPermissionForm(instance=board.permissions)

    context = {
        'board': board,
        'form': form,
    }
    return render(request, 'boards/edit_permissions.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_evidence(request, board_id):
    """Return a view of adding evidence (with a source), or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if 'add_elements' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    require_source = getattr(settings, 'EVIDENCE_REQUIRE_SOURCE', True)

    if request.method == 'POST':
        evidence_form = EvidenceForm(request.POST)
        source_form = EvidenceSourceForm(request.POST)
        if evidence_form.is_valid() and source_form.is_valid():
            with transaction.atomic():
                evidence = evidence_form.save(commit=False)
                evidence.board = board
                evidence.creator = request.user
                evidence.save()

                if source_form.cleaned_data.get('source_url'):
                    source = source_form.save(commit=False)
                    source.evidence = evidence
                    source.uploader = request.user
                    source.save()
                    fetch_source_metadata.delay(source.id)

                BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                    'is_contributor': True,
                })
            notify_add(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        evidence_form = EvidenceForm()
        source_form = EvidenceSourceForm(require=require_source, initial={'corroborating': True})

    context = {
        'board': board,
        'evidence_form': evidence_form,
        'source_form': source_form,
    }
    return render(request, 'boards/add_evidence.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_evidence(request, evidence_id):
    """Return a view for editing a piece of evidence, or handle for submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    # don't care that the board might have been removed
    board = evidence.board
    check_edit_authorization(request, board=board, has_creator=evidence)

    if request.method == 'POST':
        form = EvidenceForm(request.POST, instance=evidence)
        if 'remove' in form.data:
            return _remove_and_redirect(request, evidence, evidence.evidence_desc)

        elif form.is_valid():
            form.save()
            messages.success(request, _('Updated evidence description and date.'))
            notify_edit(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence.id,)))

    else:
        form = EvidenceForm(instance=evidence)

    context = {
        'form': form,
        'evidence': evidence,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_evidence.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_source(request, evidence_id):
    """Return a view for adding a corroborating/contradicting source, or handle form submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    if request.method == 'POST':
        form = EvidenceSourceForm(request.POST)
        if form.is_valid():
            source = form.save(commit=False)
            source.evidence = evidence
            source.uploader = request.user
            source.save()
            fetch_source_metadata.delay(source.id)
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
        else:
            corroborating = form.data['corroborating'] == 'True'
    else:
        corroborating = request.GET.get('kind') is None or request.GET.get('kind') != 'conflicting'
        form = EvidenceSourceForm(initial={'corroborating': corroborating})

    context = {
        'form': form,
        'evidence': evidence,
        'corroborating': corroborating
    }

    return render(request, 'boards/add_source.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def toggle_source_tag(request, evidence_id, source_id):
    """Toggle source tag for the given source and redirect to the evidence detail page for the associated evidence."""
    # May want to put in a sanity check here that source_id actually corresponds to evidence_id
    # Inefficient to have to do the DB lookup before making a modification. May want to have the client pass in
    # whether or not they're adding/removing the tag
    if request.method == 'POST':
        with transaction.atomic():
            source = get_object_or_404(EvidenceSource, pk=source_id)
            tag = EvidenceSourceTag.objects.get(tag_name=request.POST['tag'])
            user_tag = AnalystSourceTag.objects.filter(source=source, tagger=request.user, tag=tag)
            if user_tag.count() > 0:
                user_tag.delete()
                messages.success(request, _('Removed "{name}" tag from source.').format(name=tag.tag_name))
            else:
                AnalystSourceTag.objects.create(source=source, tagger=request.user, tag=tag)
                messages.success(request, _('Added "{name}" tag to source.').format(name=tag.tag_name))
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
    else:
        # Redirect to the form where the user can toggle a source tag
        return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def clear_notifications(request):
    """Handle POST request to clear notifications and redirect user to their profile."""
    if request.method == 'POST':
        if 'clear' in request.POST:
            request.user.notifications.mark_all_as_read()
            messages.success(request, _('Cleared all notifications.'))
    return HttpResponseRedirect('/accounts/profile')


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def evidence_detail(request, evidence_id):
    """Return a view displaying detailed information about a piece of evidence and its sources."""
    # NOTE: cannot cache page for logged in users b/c comments section contains CSRF and other protection mechanisms.
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    available_tags = EvidenceSourceTag.objects.all()
    sources = EvidenceSource.objects.filter(evidence=evidence).order_by('-source_date').select_related('uploader')
    all_tags = AnalystSourceTag.objects.filter(source__in=sources)

    source_tags = defaultdict(list)
    user_tags = defaultdict(list)
    for tag in all_tags:
        key = (tag.source_id, tag.tag_id)
        source_tags[key].append(tag)
        if tag.tagger_id == request.user.id:
            user_tags[key].append(tag)

    context = {
        'evidence': evidence,
        'sources': sources,
        'source_tags': source_tags,
        'user_tags': user_tags,
        'available_tags': available_tags,
        'meta_description': _("Analysis of evidence: {description}").format(description=evidence.evidence_desc)
    }
    return render(request, 'boards/evidence_detail.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_hypothesis(request, board_id):
    """Return a view for adding a hypothesis, or handle form submission."""
    board = get_object_or_404(Board, pk=board_id)
    existing = Hypothesis.objects.filter(board=board)

    if 'add_elements' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            hypothesis = form.save(commit=False)
            hypothesis.board = board
            hypothesis.creator = request.user
            hypothesis.save()
            BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                'is_contributor': True,
            })
            notify_add(board, actor=request.user, action_object=hypothesis)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm()

    context = {
        'form': form,
        'board': board,
        'hypotheses': existing,
    }
    return render(request, 'boards/add_hypothesis.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_hypothesis(request, hypothesis_id):
    """Return a view for editing a hypothesis, or handle board submission."""
    hypothesis = get_object_or_404(Hypothesis, pk=hypothesis_id)
    # don't care if the board has been removed
    board = hypothesis.board
    check_edit_authorization(request, board, hypothesis)

    if request.method == 'POST':
        form = HypothesisForm(request.POST, instance=hypothesis)
        if 'remove' in form.data:
            return _remove_and_redirect(request, hypothesis, hypothesis.hypothesis_text)

        elif form.is_valid():
            form.save()
            messages.success(request, _('Updated hypothesis: {text}').format(text=form.cleaned_data['hypothesis_text']))  # nopep8
            notify_edit(board, actor=request.user, action_object=hypothesis)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm(instance=hypothesis)

    context = {
        'form': form,
        'hypothesis': hypothesis,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_hypothesis.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def private_profile(request):
    """Return a view of the private profile associated with the authenticated user and handle settings."""
    user = request.user

    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=user.settings)
        if form.is_valid():
            form.save()
            messages.success(request, _('Updated account settings.'))
    else:
        form = SettingsForm(instance=user.settings)

    context = {
        'user': user,
        'boards_created': user_boards_created(user, viewing_user=user)[:5],
        'boards_contributed': user_boards_contributed(user, viewing_user=user),
        'board_voted': user_boards_evaluated(user, viewing_user=user),
        'meta_description': _('Account profile for user {name}').format(name=user),
        'notifications': request.user.notifications.unread(),
        'settings_form': form,
    }
    return render(request, 'boards/profile.html', context)


@require_safe
@cache_page(PAGE_CACHE_TIMEOUT_SECONDS)
def public_profile(request, account_id):
    """Return a view of the public profile associated with account_id."""
    user = get_object_or_404(User, pk=account_id)
    context = {
        'user': user,
        'boards_created': user_boards_created(user, viewing_user=request.user)[:5],
        'boards_contributed': user_boards_contributed(user, viewing_user=request.user),
        'board_voted': user_boards_evaluated(user, viewing_user=request.user),
        'meta_description': _("Account profile for user {name}").format(name=user),
    }
    return render(request, 'boards/public_profile.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@account_required
def profile(request, account_id):
    """Return a view of the profile associated with account_id.

    If account_id corresponds to the authenticated user, return the private profile view. Otherwise return the public
    profile.
    """
    return private_profile(request) if request.user.id == int(account_id) else public_profile(request, account_id)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def evaluate(request, board_id, evidence_id):
    """Return a view for assessing a piece of evidence against all hypotheses.

    Take a couple measures to reduce bias: (1) do not show the analyst their previous assessment, and (2) show
    the hypotheses in a random order.
    """
    # Would be nice if we could refactor this and the view to use formsets. Not obvious how to handle the shuffling
    # of the indices that way

    board = get_object_or_404(Board, pk=board_id)

    if 'read_board' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    evidence = get_object_or_404(Evidence, pk=evidence_id)

    default_eval = '------'
    keep_eval = '-- ' + _('Keep Previous Assessment')
    remove_eval = '-- ' + _('Remove Assessment')

    evaluations = {e.hypothesis_id: e for e in
                   Evaluation.objects.filter(board=board_id, evidence=evidence_id, user=request.user)}

    hypotheses = [(h, evaluations.get(h.id, None)) for h in Hypothesis.objects.filter(board=board_id)]

    evaluation_set = set([str(m.value) for m in Eval])

    if request.method == 'POST':
        with transaction.atomic():
            for hypothesis, dummy_evaluation in hypotheses:
                select = request.POST['hypothesis-{}'.format(hypothesis.id)]
                if select == remove_eval:
                    Evaluation.objects.filter(
                        board=board_id,
                        evidence=evidence,
                        user=request.user,
                        hypothesis_id=hypothesis.id,
                    ).delete()
                elif select in evaluation_set:
                    Evaluation.objects.update_or_create(
                        board=board,
                        evidence=evidence,
                        hypothesis=hypothesis,
                        user=request.user,
                        defaults={'value': select}
                    )
                else:
                    # don't add/update the evaluation
                    pass
            BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                'is_evaluator': True,
            })

        messages.success(request, _('Recorded evaluations for evidence: {desc}').format(desc=evidence.evidence_desc))
        return HttpResponseRedirect(reverse('openach:detail', args=(board_id,)))
    else:
        new_hypotheses = [h for h in hypotheses if h[1] is None]
        old_hypotheses = [h for h in hypotheses if h[1] is not None]
        random.shuffle(old_hypotheses)
        random.shuffle(new_hypotheses)
        context = {
            'board': board,
            'evidence': evidence,
            'hypotheses': new_hypotheses + old_hypotheses,
            'options': Evaluation.EVALUATION_OPTIONS,
            'default_eval': default_eval,
            'keep_eval': keep_eval,
            'remove_eval': remove_eval,
        }
        return render(request, 'boards/evaluate.html', context)


@require_safe
def robots(request):
    """Return the robots.txt including the sitemap location (using the site domain) if the site is public."""
    private_instance = getattr(settings, 'ACCOUNT_REQUIRED', False)
    context = {
        'sitemap': (
            ''.join(['https://', get_current_site(request).domain, reverse('django.contrib.sitemaps.views.sitemap')])
            if not private_instance
            else None
        ),
        'disallow_all': private_instance,
    }
    return render(request, 'robots.txt', context, content_type='text/plain')


@require_safe
def certbot(dummy_request, challenge_key):  # pragma: no cover
    """Return a response to the Let's Encrypt Certbot challenge.

    If the challenge is not configured, raise a 404. For more information, please see:
        https://certbot.eff.org/
    """
    # ignore coverage since keys aren't available in the testing environment
    public_key = getattr(settings, 'CERTBOT_PUBLIC_KEY')
    secret_key = getattr(settings, 'CERTBOT_SECRET_KEY')
    if public_key and secret_key and public_key == challenge_key:
        return HttpResponse(secret_key)
    elif public_key and not secret_key:
        raise ImproperlyConfigured("CERTBOT_SECRET_KEY not set")
    else:
        raise Http404()


@require_safe
@etag(lambda r: getattr(settings, 'DONATE_BITCOIN_ADDRESS', ''))
@cache_page(60 * 60)
def bitcoin_qrcode(request):
    """Return a QR Code for donating via Bitcoin."""
    # NOTE: if only etag is set, Django doesn't include cache headers
    address = getattr(settings, 'DONATE_BITCOIN_ADDRESS', None)
    if address:
        raw = make_qr_code(bitcoin_donation_url(get_current_site(request).name, address))
        return HttpResponse(raw.getvalue(), content_type='image/svg+xml')
    else:
        raise Http404


@require_safe
def board_search(request):
    """Return filtered boards list data in json format."""
    query = request.GET.get('query', '')
    search = Q(board_title__contains=query) | Q(board_desc__contains=query)
    queryset = Board.objects.user_readable(request.user).filter(search)[:BOARD_SEARCH_RESULTS_MAX]
    boards = json.dumps([{
            'board_title': board.board_title,
            'board_desc': board.board_desc,
            'url': reverse('openach:detail', args=(board.id,))
        } for board in queryset])
    return HttpResponse(boards, content_type='application/json')
