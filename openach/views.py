"""openach Views Configuration

For more information, please see:
    https://docs.djangoproject.com/en/1.10/topics/http/views/
"""
from collections import defaultdict
import logging
import itertools
import random

from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django import forms
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_safe
from slugify import slugify
from field_history.models import FieldHistory


from .models import Board, Hypothesis, Evidence, EvidenceSource, Evaluation, Eval, AnalystSourceTag, EvidenceSourceTag
from .models import ProjectNews
from .models import EVIDENCE_MAX_LENGTH, HYPOTHESIS_MAX_LENGTH, URL_MAX_LENGTH, SLUG_MAX_LENGTH
from .models import BOARD_TITLE_MAX_LENGTH, BOARD_DESC_MAX_LENGTH
from .metrics import consensus_vote, inconsistency, diagnosticity, calc_disagreement
from .decorators import cache_if_anon, cache_on_auth, account_required


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

PAGE_CACHE_TIMEOUT_SECONDS = 60
DEBUG = getattr(settings, 'DEBUG', False)
ACCOUNT_REQUIRED = getattr(settings, 'ACCOUNT_REQUIRED', False)


def check_owner_authorization(request, board, has_creator=None):
    """Raises a PermissionDenied exception if the authenticated user does not have edit rights for the resource"""
    if request.user.is_staff or request.user == board.creator or (has_creator and request.user == has_creator.creator):
        pass
    else:
        raise PermissionDenied()


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def index(request):
    """Returns a homepage showing project information, news, and recent boards."""
    # Show all of the boards until we can implement tagging, search, etc.
    latest_board_list = Board.objects.order_by('-pub_date')
    latest_project_news = ProjectNews.objects.filter(pub_date__lte=timezone.now()).order_by('-pub_date')[:5]
    context = {
        'latest_board_list': latest_board_list,
        'latest_project_news': latest_project_news,
    }
    return render(request, 'boards/index.html', context)


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def about(request):
    """Returns an about page showing contribution, licensing, contact, and other information."""
    return render(request, 'boards/about.html')


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def detail(request, board_id, dummy_board_slug=None):
    """
    View the board details. Evidence is sorted in order of diagnosticity. Hypotheses are sorted in order of
    consistency.
    """
    # NOTE: Django's page cache considers full URL including dummy_board_slug. In the future, we may want to adjust
    # the page key to only consider the id and the query parameters.
    # https://docs.djangoproject.com/en/1.10/topics/cache/#the-per-view-cache
    # NOTE: cannot cache page for logged in users b/c comments section contains CSRF and other protection mechanisms.
    view_type = 'average' if request.GET.get('view_type') is None else request.GET['view_type']

    board = get_object_or_404(Board, pk=board_id)
    votes = Evaluation.objects.filter(board=board).select_related('user')

    participants = set(map(lambda x: x.user, votes))

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
        return list(map(lambda f: (f, func(map(lambda s: keyed[key(f, s)], second))), first))
    hypotheses = list(board.hypothesis_set.all())
    evidence = list(board.evidence_set.all())
    hypothesis_consistency = _group(hypotheses, evidence, inconsistency, key=lambda h, e: (e, h))
    evidence_diagnosticity = _group(evidence, hypotheses, diagnosticity, key=lambda e, h: (e, h))

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
        'debug_stats': DEBUG
    }
    return render(request, 'boards/detail.html', context)


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def board_history(request, board_id):
    """Return the modification history (board details, evidence, hypotheses) for the board"""
    # this approach to grabbing the history will likely be too slow for big boards
    def _get_history(models):
        return itertools.chain(*map(lambda x: list(FieldHistory.objects.get_for_model(x).select_related('user')), models))
    board = get_object_or_404(Board, pk=board_id)
    history = [
        _get_history([board]),
        _get_history(Evidence.objects.filter(board=board)),
        _get_history(Hypothesis.objects.filter(board=board)),
    ]
    history = list(itertools.chain(*history))
    history.sort(key=lambda x: x.date_created, reverse=True)
    return render(request, 'boards/board_audit.html', {'board': board, 'history': history})


class BoardForm(forms.Form):
    """Board creation form. Users must specify at two competing hypotheses"""
    board_title = forms.CharField(label='Board Title', max_length=BOARD_TITLE_MAX_LENGTH)
    board_desc = forms.CharField(label='Board Description', max_length=BOARD_DESC_MAX_LENGTH, widget=forms.Textarea)
    hypothesis1 = forms.CharField(label='Hypothesis #1', max_length=HYPOTHESIS_MAX_LENGTH)
    hypothesis2 = forms.CharField(label='Hypothesis #2', max_length=HYPOTHESIS_MAX_LENGTH)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def create_board(request):
    """Shows form for board creation and handles form submission."""
    if request.method == 'POST':
        form = BoardForm(request.POST)
        if form.is_valid():
            time = timezone.now()
            with transaction.atomic():
                board = Board.objects.create(
                    board_title=form.cleaned_data['board_title'],
                    board_slug=slugify(form.cleaned_data['board_title'], max_length=SLUG_MAX_LENGTH),
                    board_desc=form.cleaned_data['board_desc'],
                    creator=request.user,
                    pub_date=time
                )
                for hypothesis_key in ['hypothesis1', 'hypothesis2']:
                    Hypothesis.objects.create(
                        board=board,
                        hypothesis_text=form.cleaned_data[hypothesis_key],
                        submit_date=time,
                    )

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
    """Shows form for editing a board and handles form submission"""
    board = get_object_or_404(Board, pk=board_id)
    check_owner_authorization(request, board)

    if request.method == 'POST':
        form = BoardEditForm(request.POST)
        if form.is_valid():
            board.board_title = form.cleaned_data['board_title']
            board.board_desc = form.cleaned_data['board_desc']
            board.board_slug = slugify(form.cleaned_data['board_title'], max_length=SLUG_MAX_LENGTH)
            board.save()
            messages.success(request, 'Updated board title and/or description.')
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardEditForm(initial={'board_title': board.board_title, 'board_desc': board.board_desc})
    return render(request, 'boards/edit_board.html', {'form': form, 'board': board})


class EvidenceEditForm(forms.Form):
    """Form for modifying the basic evidence information"""
    evidence_desc = forms.CharField(
        label='Evidence', max_length=EVIDENCE_MAX_LENGTH,
        help_text='A short summary of the evidence. Use the Event Date field for capturing the date'
    )
    event_date = forms.DateField(
        label='Event Date',
        help_text='The date the event occurred or started',
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )


class BaseSourceForm(forms.Form):
    """Form for adding a source to a piece of evidence"""
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
    """
    Form to add a new piece of evidence. The evidence provided must have at least one source.
    The analyst can provide additional sources later.
    """
    pass


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_evidence(request, board_id):
    """
    View to add a new piece of evidence (with a source) to the specified board.
    """
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
                EvidenceSource.objects.create(
                    evidence=evidence,
                    source_url=form.cleaned_data['evidence_url'],
                    source_date=form.cleaned_data['evidence_date'],
                    uploader=request.user,
                    corroborating=True,
                    submit_date=submit_date
                )

            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = EvidenceForm()

    return render(request, 'boards/add_evidence.html', {'form': form, 'board': board})


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_evidence(request, evidence_id):
    """Shows a form for editing a piece of evidence and handles form submission"""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    board = evidence.board
    check_owner_authorization(request, board=board, has_creator=evidence)

    if request.method == 'POST':
        form = EvidenceEditForm(request.POST)
        if form.is_valid():
            evidence.evidence_desc = form.cleaned_data['evidence_desc']
            evidence.event_date = form.cleaned_data['event_date']
            evidence.save()
            messages.success(request, 'Updated evidence description and/or date.')
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = EvidenceEditForm(initial={'evidence_desc': evidence.evidence_desc, 'event_date': evidence.event_date})
    return render(request, 'boards/edit_evidence.html', {'form': form, 'evidence': evidence, 'board': board})


class EvidenceSourceForm(BaseSourceForm):
    """
    Form for editing a corroborating/contradicting source for a piece of evidence. By default sources are
    corroborating.
    """
    corroborating = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput()
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_source(request, evidence_id):
    """Shows a form for adding a corroborating/contradicting source for a piece of evidence and handles submission."""
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


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def evidence_detail(request, evidence_id):
    """Show detailed information about a piece of information and its sources"""
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
    """Form for a board hypothesis"""
    hypothesis_text = forms.CharField(label='Hypothesis', max_length=200)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def add_hypothesis(request, board_id):
    """Shows a form for adding a hypothesis to a board and handles form submission"""
    board = get_object_or_404(Board, pk=board_id)
    existing = Hypothesis.objects.filter(board=board)

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            Hypothesis.objects.create(
                hypothesis_text=form.cleaned_data['hypothesis_text'],
                board=board,
                creator=request.user,
                submit_date=timezone.now(),
            )
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
    """Shows a form for editing a hypothesis and handles board submission."""
    hypothesis = get_object_or_404(Hypothesis, pk=hypothesis_id)
    board = hypothesis.board
    check_owner_authorization(request, board, hypothesis)

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            hypothesis.hypothesis_text = form.cleaned_data['hypothesis_text']
            hypothesis.save()
            messages.success(request, 'Updated hypothesis.')
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm(initial={'hypothesis_text': hypothesis.hypothesis_text})
    return render(request, 'boards/edit_hypothesis.html', {'form': form, 'hypothesis': hypothesis, 'board': board})


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def profile(request, account_id=None):
    """
    Show the private/public profile for account_id. If account_id is None, shows the private profile for the logged in
    user. If account is specified and the user is not logged in, raise a 404.
    """
    # TODO: cache the page based on whether user is viewing private profile or public profile
    account_id = request.user.id if request.user and not account_id else account_id

    # There's no real reason for these to be atomic
    user = get_object_or_404(User, pk=account_id)
    boards = Board.objects.filter(creator=user)
    evidence = Evidence.objects.filter(creator=user)
    hypotheses = Hypothesis.objects.filter(creator=user)
    votes = Evaluation.objects.filter(user=user)
    contributed = set(map(lambda x: x.board, evidence)).union(set(map(lambda x: x.board, hypotheses)))
    voted = set(map(lambda x: x.board, votes))
    context = {
        'user': user,
        'boards_created': boards,
        'boards_contributed': contributed,
        'board_voted': voted,
        'meta_description': "Account profile for user {}".format(user)
    }

    template = 'profile.html' if request.user and request.user.id == account_id else 'public_profile.html'
    return render(request, 'boards/' + template, context)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def evaluate(request, board_id, evidence_id):
    """
    View for assessing a piece of evidence against all of the hypotheses. A couple measures are taken to attempt to
    reduce bias: (1) the analyst is not shown their previous assessment, and (2) the hypotheses are shown in a random
    order.
    """
    # FIXME: need to fix the db transaction structure for this method
    default_eval = '------'
    board = get_object_or_404(Board, pk=board_id)
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    hypotheses = list(Hypothesis.objects.filter(board=board_id))
    random.shuffle(hypotheses)

    if request.method == 'POST':
        with transaction.atomic():
            # Remove user's previous votes for the the piece of evidence
            Evaluation.objects.filter(board=board_id, evidence=evidence_id, user=request.user).delete()

            # Add new votes for the hypotheses
            for hypothesis in hypotheses:
                select = request.POST['hypothesis-{}'.format(hypothesis.id)]
                if select != default_eval:
                    Evaluation.objects.create(
                        board=board,
                        evidence=evidence,
                        hypothesis=hypothesis,
                        user=request.user,
                        value=select
                    )

        return HttpResponseRedirect(reverse('openach:detail', args=(board_id,)))
    else:
        context = {
            'board': board,
            'evidence': evidence,
            'hypotheses': hypotheses,
            'options': Evaluation.EVALUATION_OPTIONS,
            'default_eval': default_eval
        }
        return render(request, 'boards/evaluate.html', context)


@require_safe
def robots(request):
    """Returns the robots.txt including the sitemap location (using the site domain)"""
    context = {
        'sitemap': (
            ''.join(['https://', get_current_site(request).domain, reverse('django.contrib.sitemaps.views.sitemap')])
            if not ACCOUNT_REQUIRED
            else None
        ),
        'disallow_all': ACCOUNT_REQUIRED,
    }
    return render(request, 'robots.txt', context, content_type='text/plain')


@require_safe
def certbot(dummy_request, challenge_key):  # pragma: no cover
    """Respond to the Let's Encrypt certbot challenge. If the challenge is not configured, returns a 404"""
    # ignore coverage since keys aren't available in the testing environment
    public_key = getattr(settings, 'CERTBOT_PUBLIC_KEY')
    secret_key = getattr(settings, 'CERTBOT_SECRET_KEY')
    if public_key and secret_key and public_key == challenge_key:
        return HttpResponse(secret_key)
    elif public_key and not secret_key:
        raise ImproperlyConfigured("CERTBOT_SECRET_KEY not set")
    else:
        raise Http404()
