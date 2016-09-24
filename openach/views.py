"""Analysis of Competing Hypotheses Django Application Views Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/topics/http/views/
"""
from collections import defaultdict
import logging
import itertools
import random
from io import BytesIO

from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django import forms
from django.utils import timezone
from django.utils.http import urlencode
from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
# NOTE: django.core.urlresolvers was deprecated in Django 1.10. Landscape is loading version 1.9.9 for some reason
from django.urls import reverse  # pylint: disable=no-name-in-module
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_safe
from django.forms import ValidationError
from django.utils.translation import ugettext as _
from django.views.decorators.http import etag
from django.views.decorators.cache import cache_page
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from slugify import slugify
from field_history.models import FieldHistory
import qrcode
from qrcode.image.svg import SvgPathImage
from notifications.signals import notify

from .models import Board, Hypothesis, Evidence, EvidenceSource, Evaluation, Eval, AnalystSourceTag, EvidenceSourceTag
from .models import ProjectNews, BoardFollower
from .models import EVIDENCE_MAX_LENGTH, HYPOTHESIS_MAX_LENGTH, URL_MAX_LENGTH, SLUG_MAX_LENGTH
from .models import BOARD_TITLE_MAX_LENGTH, BOARD_DESC_MAX_LENGTH
from .metrics import consensus_vote, inconsistency, diagnosticity, calc_disagreement
from .metrics import generate_contributor_count, generate_evaluator_count
from .metrics import user_boards_contributed, user_boards_created, user_boards_evaluated
from .decorators import cache_if_anon, cache_on_auth, account_required
from .auth import check_edit_authorization


# XXX: allow_remove logic should probably be refactored to a template context processor

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

PAGE_CACHE_TIMEOUT_SECONDS = 60
DEBUG = getattr(settings, 'DEBUG', False)

DEFAULT_EVAL = '------'
KEEP_EVAL = '-- Keep Previous Assessment'
REMOVE_EVAL = '-- Remove Assessment'


def is_field_provided(form, field):
    """Return true if field has non-None value in the form."""
    return field in form.cleaned_data and form.cleaned_data[field] is not None


def _remove_and_redirect(request, removable, message_detail):
    """Mark a model as removed and redirect the user to the associated board detail page."""
    if getattr(settings, 'EDIT_REMOVE_ENABLED', True):
        removable.removed = True
        removable.save()
        klass_name = removable._meta.verbose_name.title()  # pylint: disable=protected-access
        klass = klass_name[:1].lower() + klass_name[1:] if klass_name else ''
        messages.success(request, 'Removed {}: {}'.format(klass, message_detail))
        return HttpResponseRedirect(reverse('openach:detail', args=(removable.board.id,)))
    else:
        raise PermissionDenied()


def bitcoin_donation_url(address):
    """Return a Bitcoin donation URL for DONATE_BITCOIN_ADDRESS or None."""
    if address:
        msg = "Donate to {}".format(Site.objects.get_current().name)
        url = "bitcoin:{}?{}".format(address, urlencode({'message': msg}))
        return url
    else:
        return None


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
    """Notify board followers of an action."""
    for follow in board.followers.all().select_related('user'):
        if follow.user != actor:
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
    latest_board_list = Board.objects.order_by('-pub_date')[:5]
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
    board_list = Board.objects.order_by('-pub_date')
    metric_timeout_seconds = 60 * 2

    desc = 'List of intelligence boards on {} and summary information'.format(Site.objects.get_current().name)
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
        None: lambda x: ('contributed to', user_boards_contributed(x)),
        'created': lambda x: ('created', user_boards_created(x)),
        'evaluated': lambda x: ('evaluated', user_boards_evaluated(x)),
        'contribute': lambda x: ('contributed to', user_boards_contributed(x)),
    }

    user = get_object_or_404(User, pk=account_id)
    query = request.GET.get('query')
    verb, board_list = queries.get(query, queries[None])(user)
    desc = 'List of intelligence boards user {} has {}'.format(user.username, verb)
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
    privacy_url = getattr(settings, 'PRIVACY_URL', None)
    context = {
        'bitcoin_address': address,
        'bitcoin_donate_url': bitcoin_donation_url(address),
        'privacy_url': privacy_url,
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
    view_type = 'average' if request.GET.get('view_type') is None else request.GET['view_type']

    board = get_object_or_404(Board, pk=board_id)
    votes = Evaluation.objects.filter(board=board).select_related('user')

    participants = {vote.user for vote in votes}

    # calculate consensus and disagreement for each evidence/hypothesis pair
    def _pair_key(evaluation):
        return evaluation.evidence_id, evaluation.hypothesis_id
    keyed = defaultdict(list)
    for vote in votes:
        keyed[_pair_key(vote)].append(Eval.for_value(vote.value))
    consensus = {k: consensus_vote(v) for k, v in keyed.items()}
    disagreement = {k: calc_disagreement(v) for k, v in keyed.items()}

    user_votes = (
        {_pair_key(v): Eval.for_value(v.value) for v in votes.filter(user=request.user)}
        if request.user.is_authenticated
        else None)

    # augment hypotheses and evidence with diagnosticity and consistency
    def _group(first, second, func, key):
        return [(f, func([keyed[key(f, s)] for s in second])) for f in first]
    hypotheses = list(board.hypothesis_set.filter(removed=False))
    evidence = list(board.evidence_set.filter(removed=False))
    hypothesis_consistency = _group(hypotheses, evidence, inconsistency, key=lambda h, e: (e.id, h.id))
    evidence_diagnosticity = _group(evidence, hypotheses, diagnosticity, key=lambda e, h: (e.id, h.id))

    context = {
        'board': board,
        'evidences': sorted(evidence_diagnosticity, key=lambda e: e[1], reverse=True),
        'hypotheses': sorted(hypothesis_consistency, key=lambda h: h[1]),
        'view_type': view_type,
        'votes': consensus,
        'user_votes': user_votes,
        'disagreement': disagreement,
        'participants': participants,
        'meta_description': board.board_desc,
        'allow_share': not getattr(settings, 'ACCOUNT_REQUIRED', False),
        'debug_stats': DEBUG
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
    history = [
        _get_history([board]),
        _get_history(Evidence.all_objects.filter(board=board)),
        _get_history(Hypothesis.all_objects.filter(board=board)),
    ]
    history = list(itertools.chain(*history))
    history.sort(key=lambda x: x.date_created, reverse=True)
    return render(request, 'boards/board_audit.html', {'board': board, 'history': history})


class BoardForm(forms.Form):
    """Board creation form.

    Users must specify at two competing hypotheses.
    """

    # NOTE: pylint and pep8 disagree about the hanging indents below in the help_text

    board_title = forms.CharField(
        label='Board Title',
        max_length=BOARD_TITLE_MAX_LENGTH,
        help_text="The board title (i.e., topic). Typically phrased as a question asking about " +
                  "what happened in the past, what is happening currently, or what will happen in the future. " +  # nopep8
                  "For example: 'who/what was behind event X?' or 'what are Y's current capabilities?'"  # nopep8
    )
    board_desc = forms.CharField(
        label='Board Description',
        max_length=BOARD_DESC_MAX_LENGTH,
        widget=forms.Textarea,
        help_text="A description providing context around the topic. Helps to clarify what hypotheses " +
                  "and evidence are relevant."  # pylint: disable=bad-continuation
    )
    hypothesis1 = forms.CharField(
        label='Hypothesis #1',
        max_length=HYPOTHESIS_MAX_LENGTH,
        help_text="A hypothesis providing a potential answer to the topic question."
    )
    hypothesis2 = forms.CharField(
        label='Hypothesis #2',
        max_length=HYPOTHESIS_MAX_LENGTH,
        help_text="An alternative hypothesis providing a potential answer to the topic question."
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def create_board(request):
    """Return a board creation view, or handle the form submission."""
    if request.method == 'POST':
        form = BoardForm(request.POST)
        if form.is_valid():
            timestamp = timezone.now()
            with transaction.atomic():
                board = Board.objects.create(
                    board_title=form.cleaned_data['board_title'],
                    board_slug=slugify(form.cleaned_data['board_title'], max_length=SLUG_MAX_LENGTH),
                    board_desc=form.cleaned_data['board_desc'],
                    creator=request.user,
                    pub_date=timestamp
                )
                for hypothesis_key in ['hypothesis1', 'hypothesis2']:
                    Hypothesis.objects.create(
                        board=board,
                        hypothesis_text=form.cleaned_data[hypothesis_key],
                        submit_date=timestamp,
                    )
                BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                    'is_creator': True,
                    'update_timestamp': timestamp
                })

            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardForm()
    return render(request, 'boards/create_board.html', {'form': form})


class BoardEditForm(forms.Form):
    """Board edit form."""

    board_title = forms.CharField(label='Board Title', max_length=BOARD_TITLE_MAX_LENGTH)
    board_desc = forms.CharField(label='Board Description', max_length=BOARD_DESC_MAX_LENGTH, widget=forms.Textarea)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_board(request, board_id):
    """Return a board edit view, or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)
    check_edit_authorization(request, board)
    allow_remove = request.user.is_staff and getattr(settings, 'EDIT_REMOVE_ENABLED', True)

    if request.method == 'POST':
        form = BoardEditForm(request.POST)

        if 'remove' in form.data:
            if allow_remove:
                board.removed = True
                board.save()
                messages.success(request, 'Removed board {}'.format(board.board_title))
                return HttpResponseRedirect(reverse('openach:index'))
            else:
                raise PermissionDenied()

        elif form.is_valid():
            board.board_title = form.cleaned_data['board_title']
            board.board_desc = form.cleaned_data['board_desc']
            board.board_slug = slugify(form.cleaned_data['board_title'], max_length=SLUG_MAX_LENGTH)
            board.save()
            messages.success(request, 'Updated board title and/or description.')
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardEditForm(initial={'board_title': board.board_title, 'board_desc': board.board_desc})

    context = {
        'form': form,
        'board': board,
        'allow_remove': allow_remove
    }

    return render(request, 'boards/edit_board.html', context)


class EvidenceEditForm(forms.Form):
    """Form for modifying the basic evidence information."""

    evidence_desc = forms.CharField(
        label='Evidence', max_length=EVIDENCE_MAX_LENGTH,
        help_text='A short summary of the evidence. Use the Event Date field for capturing the date'
    )
    event_date = forms.DateField(
        label='Event Date (Optional)',
        help_text='The date the event occurred or started',
        required=False,
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )


class BaseSourceForm(forms.Form):
    """Form for adding a source to a piece of evidence."""

    evidence_url = forms.URLField(
        label='Source Website',
        help_text='A source (e.g., news article or press release) corroborating the evidence',
        max_length=URL_MAX_LENGTH
    )
    evidence_date = forms.DateField(
        label='Source Date',
        # NOTE: pylint and pep8 disagree about the hanging indent below
        help_text='The date the source released or last updated the information corroborating the evidence. ' +
                  'Typically the date of the article or post',  # pylint: disable=bad-continuation
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )


class EvidenceForm(BaseSourceForm, EvidenceEditForm):
    """Form for adding a new piece of evidence.

    If EVIDENCE_REQUIRE_SOURCE is set, the evidence provided must have a source. Analysts can provide additional
    corroborating / conflicting sources after adding the evidence.
    """

    def __init__(self, *args, **kwargs):
        """Construct an evidence form.

        Require an initial corroborating source (and date) if EVIDENCE_REQUIRE_SOURCE is True.
        """
        super().__init__(*args, **kwargs)
        if not getattr(settings, 'EVIDENCE_REQUIRE_SOURCE', True):
            self.fields['evidence_url'].required = False
            self.fields['evidence_url'].label += ' (Optional)'
            self.fields['evidence_date'].required = False
            self.fields['evidence_date'].label += ' (Optional)'

    def clean(self):
        """Require a source date if the analyst provided a source URL."""
        if is_field_provided(self, 'evidence_url') and not is_field_provided(self, 'evidence_date'):
            raise ValidationError(_('Please provide a date for the source.'), code='invalid')


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_evidence(request, board_id):
    """Return a view of adding evidence (with a source), or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if request.method == 'POST':
        form = EvidenceForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                submit_date = timezone.now()
                evidence = Evidence.objects.create(
                    evidence_desc=form.cleaned_data['evidence_desc'],
                    event_date=form.cleaned_data['event_date'],
                    board=board,
                    creator=request.user,
                    submit_date=submit_date
                )
                if is_field_provided(form, 'evidence_url') and is_field_provided(form, 'evidence_date'):
                    EvidenceSource.objects.create(
                        evidence=evidence,
                        source_url=form.cleaned_data['evidence_url'],
                        source_date=form.cleaned_data['evidence_date'],
                        uploader=request.user,
                        corroborating=True,
                        submit_date=submit_date
                    )
                BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                    'is_contributor': True,
                    'update_timestamp': submit_date
                })

            notify_add(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = EvidenceForm()

    return render(request, 'boards/add_evidence.html', {'form': form, 'board': board})


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_evidence(request, evidence_id):
    """Return a view for editing a piece of evidence, or handle for submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    # don't care that the board might have been removed
    board = evidence.board
    check_edit_authorization(request, board=board, has_creator=evidence)

    if request.method == 'POST':
        form = EvidenceEditForm(request.POST)
        if 'remove' in form.data:
            return _remove_and_redirect(request, evidence, evidence.evidence_desc)

        elif form.is_valid():
            evidence.evidence_desc = form.cleaned_data['evidence_desc']
            evidence.event_date = form.cleaned_data['event_date']
            evidence.save()
            messages.success(request, 'Updated evidence description and date.')
            notify_edit(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence.id,)))

    else:
        form = EvidenceEditForm(initial={'evidence_desc': evidence.evidence_desc, 'event_date': evidence.event_date})

    context = {
        'form': form,
        'evidence': evidence,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_evidence.html', context)


class EvidenceSourceForm(BaseSourceForm):
    """Form for editing a corroborating/contradicting source for a piece of evidence.

    The hidden corroborating field should be set by the view method before rendering the form.
    """

    corroborating = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput()
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_source(request, evidence_id):
    """Return a view for adding a corroborating/contradicting source, or handle form submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    if request.method == 'POST':
        form = EvidenceSourceForm(request.POST)
        if form.is_valid():
            EvidenceSource.objects.create(
                evidence=evidence,
                source_url=form.cleaned_data['evidence_url'],
                source_date=form.cleaned_data['evidence_date'],
                uploader=request.user,
                submit_date=timezone.now(),
                corroborating=form.cleaned_data['corroborating'],
            )
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


@require_http_methods(["HEAD", "GET", "POST"])
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
                messages.success(request, 'Removed "{}" tag from source.'.format(tag.tag_name))
            else:
                AnalystSourceTag.objects.create(source=source, tagger=request.user, tag=tag, tag_date=timezone.now())
                messages.success(request, 'Added "{}" tag to source.'.format(tag.tag_name))
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
    else:
        # Redirect to the form where the user can toggle a source tag
        return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def clear_notifications(request):
    """Handle POST request to clear notifications and redirect user to their profile."""
    if request.method == 'POST':
        if 'clear' in request.POST:
            request.user.notifications.mark_all_as_read()
            messages.success(request, 'Cleared all notifications.')
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
        'meta_description': "Analysis of evidence: {}".format(evidence.evidence_desc)
    }
    return render(request, 'boards/evidence_detail.html', context)


class HypothesisForm(forms.Form):
    """Form for a board hypothesis."""

    hypothesis_text = forms.CharField(label='Hypothesis', max_length=200)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_hypothesis(request, board_id):
    """Return a view for adding a hypothesis, or handle form submission."""
    board = get_object_or_404(Board, pk=board_id)
    existing = Hypothesis.objects.filter(board=board)

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            timestamp = timezone.now()
            hypothesis = Hypothesis.objects.create(
                hypothesis_text=form.cleaned_data['hypothesis_text'],
                board=board,
                creator=request.user,
                submit_date=timestamp,
            )
            BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                'is_contributor': True,
                'update_timestamp': timestamp
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


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_hypothesis(request, hypothesis_id):
    """Return a view for editing a hypothesis, or handle board submission."""
    hypothesis = get_object_or_404(Hypothesis, pk=hypothesis_id)
    # don't care if the board has been removed
    board = hypothesis.board
    check_edit_authorization(request, board, hypothesis)

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if 'remove' in form.data:
            return _remove_and_redirect(request, hypothesis, hypothesis.hypothesis_text)

        elif form.is_valid():
            hypothesis.hypothesis_text = form.cleaned_data['hypothesis_text']
            hypothesis.save()
            messages.success(request, 'Updated hypothesis.')
            notify_edit(board, actor=request.user, action_object=hypothesis)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm(initial={'hypothesis_text': hypothesis.hypothesis_text})

    context = {
        'form': form,
        'hypothesis': hypothesis,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_hypothesis.html', context)


@require_safe
@login_required
def private_profile(request):
    """Return a view of the private profile associated with the authenticated user."""
    user = request.user
    context = {
        'user': user,
        'boards_created': user_boards_created(user)[:5],
        'boards_contributed': user_boards_contributed(user),
        'board_voted': user_boards_evaluated(user),
        'meta_description': "Account profile for user {}".format(user),
        'notifications': request.user.notifications.unread(),
    }
    return render(request, 'boards/profile.html', context)


@require_safe
@cache_page(PAGE_CACHE_TIMEOUT_SECONDS)
def public_profile(request, account_id):
    user = get_object_or_404(User, pk=account_id)
    context = {
        'user': user,
        'boards_created': user_boards_created(user)[:5],
        'boards_contributed': user_boards_contributed(user),
        'board_voted': user_boards_evaluated(user),
        'meta_description': "Account profile for user {}".format(user),
    }
    return render(request, 'boards/public_profile.html', context)


@require_safe
@account_required
def profile(request, account_id):
    """Return a view of the profile associated with account_id.

    If account_id corresponds to the authenticated user, returns the private profile view.
    """
    return private_profile(request) if request.user.id == int(account_id) else public_profile(request, account_id)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def evaluate(request, board_id, evidence_id):
    """Return a view for assessing a piece of evidence against all hypotheses.

    Take a couple measures to reduce bias: (1) do not show the analyst their previous assessment, and (2) show
    the hypotheses in a random order.
    """
    board = get_object_or_404(Board, pk=board_id)
    evidence = get_object_or_404(Evidence, pk=evidence_id)

    evaluations = {e.hypothesis_id: e for e in
                   Evaluation.objects.filter(board=board_id, evidence=evidence_id, user=request.user)}

    hypotheses = [(h, evaluations.get(h.id, None)) for h in Hypothesis.objects.filter(board=board_id)]

    if request.method == 'POST':
        with transaction.atomic():
            timestamp = timezone.now()
            for hypothesis, dummy_evaluation in hypotheses:
                select = request.POST['hypothesis-{}'.format(hypothesis.id)]
                if select == REMOVE_EVAL:
                    Evaluation.objects.filter(
                        board=board_id,
                        evidence=evidence,
                        user=request.user,
                        hypothesis_id=hypothesis.id,
                    ).delete()
                elif select != DEFAULT_EVAL and select != KEEP_EVAL:
                    Evaluation.objects.update_or_create(
                        board=board,
                        evidence=evidence,
                        hypothesis=hypothesis,
                        user=request.user,
                        defaults={
                            'value': select,
                            'timestamp': timestamp
                        }
                    )
                else:
                    # don't add/update the evaluation
                    pass
            BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                'is_evaluator': True,
                'update_timestamp': timestamp
            })

        messages.success(request, "Recorded evaluations for evidence: {}".format(evidence.evidence_desc))
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
            'default_eval': DEFAULT_EVAL,
            'keep_eval': KEEP_EVAL,
            'remove_eval': REMOVE_EVAL,
        }
        return render(request, 'boards/evaluate.html', context)


@require_safe
def robots(request):
    """Return the robots.txt including the sitemap location (using the site domain) if the site is public."""
    private_intance = getattr(settings, 'ACCOUNT_REQUIRED', False)
    context = {
        'sitemap': (
            ''.join(['https://', get_current_site(request).domain, reverse('django.contrib.sitemaps.views.sitemap')])
            if not private_intance
            else None
        ),
        'disallow_all': private_intance,
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
def bitcoin_qrcode(dummy_request):
    """Return a QR Code for donating via Bitcoin."""
    # NOTE: if only etag is set, Django doesn't include cache headers
    address = getattr(settings, 'DONATE_BITCOIN_ADDRESS', '')
    if address:
        # https://pypi.python.org/pypi/qrcode/5.3
        logger.debug("Generating QR code for address %s", address)
        code = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # about 15% or less errors can be corrected.
            box_size=10,
            border=4,
        )
        code.add_data(bitcoin_donation_url(address))
        code.make(fit=True)
        img = code.make_image(image_factory=SvgPathImage)
        raw = BytesIO()
        img.save(raw)
        raw.flush()
        return HttpResponse(raw.getvalue(), content_type="image/svg+xml")
    else:
        raise Http404
