"""Analysis of Competing Hypotheses Django Application Views Configuration.

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
# NOTE: django.core.urlresolvers was deprecated in Django 1.10. Landscape is loading version 1.9.9 for some reason
from django.urls import reverse  # pylint: disable=no-name-in-module
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_safe
from django.forms import ValidationError
from django.utils.translation import ugettext as _
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
EVIDENCE_REQUIRE_SOURCE = getattr(settings, 'EVIDENCE_REQUIRE_SOURCE', True)

DEFAULT_EVAL = '------'
KEEP_EVAL = '-- Keep Previous Assessment'
REMOVE_EVAL = '-- Remove Assessment'


def check_owner_authorization(request, board, has_creator=None):
    """Raise a PermissionDenied exception if the authenticated user does not have edit rights for the resource."""
    if request.user.is_staff or request.user == board.creator or (has_creator and request.user == has_creator.creator):
        pass
    else:
        raise PermissionDenied()


def is_field_provided(form, field):
    """Return true if field has non-None value in the form."""
    return field in form.cleaned_data and form.cleaned_data[field] is not None


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def index(request):
    """Return a homepage view showing project information, news, and recent boards."""
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
    """Return an about view showing contribution, licensing, contact, and other information."""
    return render(request, 'boards/about.html')


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
    hypotheses = list(board.hypothesis_set.all())
    evidence = list(board.evidence_set.all())
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
        'allow_share': not ACCOUNT_REQUIRED,
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
        _get_history(Evidence.objects.filter(board=board)),
        _get_history(Hypothesis.objects.filter(board=board)),
    ]
    history = list(itertools.chain(*history))
    history.sort(key=lambda x: x.date_created, reverse=True)
    return render(request, 'boards/board_audit.html', {'board': board, 'history': history})


class BoardForm(forms.Form):
    """Board creation form.

    Users must specify at two competing hypotheses.
    """

    board_title = forms.CharField(label='Board Title', max_length=BOARD_TITLE_MAX_LENGTH)
    board_desc = forms.CharField(label='Board Description', max_length=BOARD_DESC_MAX_LENGTH, widget=forms.Textarea)
    hypothesis1 = forms.CharField(label='Hypothesis #1', max_length=HYPOTHESIS_MAX_LENGTH)
    hypothesis2 = forms.CharField(label='Hypothesis #2', max_length=HYPOTHESIS_MAX_LENGTH)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def create_board(request):
    """Return a board creation view, or handle the form submission."""
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
    """Return a board edit view, or handle the form submission."""
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
        super().__init__(*args, **kwargs)
        if not EVIDENCE_REQUIRE_SOURCE:
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

            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = EvidenceForm()

    return render(request, 'boards/add_evidence.html', {'form': form, 'board': board})


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_evidence(request, evidence_id):
    """Return a view for editing a piece of evidence, or handle for submission."""
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
    """Return a view for editing a hypothesis, or handle board submission."""
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
    """Return a view of the private or public profile associated with account_id.

    If account_id is None, show the private profile for the logged in user. If account is specified and the user is not
    logged in, raise a 404.
    """
    # TODO: cache the page based on whether user is viewing private profile or public profile
    account_id = request.user.id if request.user and not account_id else account_id

    # There's no real reason for these to be atomic
    user = get_object_or_404(User, pk=account_id)
    boards = Board.objects.filter(creator=user)
    evidence = Evidence.objects.filter(creator=user).select_related('board')
    hypotheses = Hypothesis.objects.filter(creator=user).select_related('board')
    votes = Evaluation.objects.filter(user=user).select_related('board')
    contributed = {e.board for e in evidence}.union({h.board for h in hypotheses})
    voted = {v.board for v in votes}
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
            for hypothesis, _ in hypotheses:
                select = request.POST['hypothesis-{}'.format(hypothesis.id)]
                if select == REMOVE_EVAL:
                    Evaluation.objects.filter(
                        board=board_id,
                        evidence=evidence,
                        user=request.user,
                        hypothesis_id=hypothesis.id
                    ).delete()
                elif select != DEFAULT_EVAL and select != KEEP_EVAL:
                    Evaluation.objects.update_or_create(
                        board=board,
                        evidence=evidence,
                        hypothesis=hypothesis,
                        user=request.user,
                        defaults={
                            'value': select
                        }
                    )
                else:
                    # don't add/update the evaluation
                    pass
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
