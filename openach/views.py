from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Board, Hypothesis, Evidence, EvidenceSource, Evaluation, Eval, AnalystSourceTag, EvidenceSourceTag
from .models import ProjectNews
from collections import defaultdict
from django.db import transaction
import logging
import itertools
from django.urls import reverse
import statistics
from django import forms
from django.utils import timezone
from openintel.settings import DEBUG, CERTBOT_PUBLIC_KEY, CERTBOT_SECRET_KEY, SLUG_MAX_LENGTH
from django.contrib import messages
from slugify import slugify
from django.contrib.sites.shortcuts import get_current_site
import random


logger = logging.getLogger(__name__)


def index(request):
    """ Returns a basic homepage showing all of the board """
    # Show all of the boards until we can implement tagging, search, etc.
    latest_board_list = Board.objects.order_by('-pub_date')
    latest_project_news = ProjectNews.objects.filter(pub_date__lte=timezone.now()).order_by('-pub_date')[:5]
    context = {
        'latest_board_list': latest_board_list,
        'latest_project_news': latest_project_news,
    }
    return render(request, 'boards/index.html', context)


def about(request):
    return render(request, 'boards/about.html')


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and true entries"""
    # https://stackoverflow.com/questions/8793772/how-to-split-a-sequence-according-to-a-predicate
    # NOTE: this might iterate over the collection twice
    t1, t2 = itertools.tee(iterable)
    return itertools.filterfalse(pred, t1), filter(pred, t2)


def mean_na_neutral_vote(evaluations):
    """
    Returns the mean rating on a 1-5 scale for the given evaluations, or None if there are no evaluations. Treats N/As
    as a neutral vote.
    """
    def replace_na(x): return x.value if (x and x is not Eval.not_applicable) else Eval.neutral.value
    return statistics.mean(map(replace_na, evaluations)) if evaluations else None


def calc_disagreement(evaluations):
    """
    Determine the disagreement for a set of evaluations. Determined as the max disagreement of (1) N/A and non-N/A
    responses and (2) non-N/A evaluations
    :param evaluations: an iterable of Eval
    """
    if evaluations:
        na_it, rated_it = partition(lambda x: x is not Eval.not_applicable, evaluations)
        na = list(na_it)
        rated = list(rated_it)

        # Here we use the sample standard deviation because we consider the evaluations are a sample of all the
        # evaluations that could be given.
        # Not clear the best way to make the N/A disagreement comparable to the evaluation disagreement calculation
        na_disagreement = statistics.stdev(([0] * len(na)) + ([1] * len(rated))) if len(na) + len(rated) > 1 else 0.0
        non_na_disagreement = statistics.stdev(map(lambda x: x.value, rated)) if len(rated) > 1 else 0.0
        return max(na_disagreement, non_na_disagreement)
    else:
        return None


def consensus_vote(evaluations):
    """
    Determine the consensus Eval given an iterable of Eval. (1) whether or not the evidence is applicable, and
    (2) if the evidence is applicable, how consistent the evidence is with the hypothesis. Is conservative, adjusting
    the result toward Eval.neutral if there is a "tie".
    """
    na_it, rated_it = partition(lambda x: x is not Eval.not_applicable, evaluations)
    na = list(na_it)
    rated = list(rated_it)

    if not na and not rated:
        return None
    elif len(na) > len(rated):
        return Eval.not_applicable
    else:
        consensus = round(statistics.mean(map(lambda x: x.value, rated)))
        return Eval.for_value(round(consensus))


def inconsistency(evaluations):
    """
    Calculate a metric for the inconsistency of a hypothesis with respect to a set of evidence. Does not account for
    the reliability of the evidence (e.g., due to deception). Metric is monotonic in the number of pieces of evidence
    that have been evaluated. That is, for a given hypothesis, further evidence can only serve to refute it (though
    it may make the hypothesis more likely relative to the other hypotheses).
    :param evaluations: an iterable of sets of Eval for the hypothesis
    """
    # The "inconsistency" needs to capture the extent to which a hypothesis has been refuted. The approach below
    # computes a metric similar to "sum squared error" for evidence where the consensus is that the hypotheses is
    # inconsistent. Currently we're treating N/A's a neutral. It may make sense to exclude them entirely because a
    # hypotheses can be considered more consistent just because there's less evidence that applies to it.
    na_neutral_consensuses = list(map(mean_na_neutral_vote, evaluations))
    inconsistent = list(filter(lambda x: x is not None and x < Eval.neutral.value, na_neutral_consensuses))
    return sum(map(lambda x: (Eval.neutral.value - x)**2, inconsistent))


def diagnosticity(evaluations):
    """
    Calculate the diagnosticity of a piece of evidence given its evaluation vs. a set of hypotheses.
    :param evaluations: an iterable of sets of Eval for a piece of evidence
    """
    # The "diagnosticity" needs to capture how well the evidence separates/distinguishes the hypotheses. If we don't
    # show a preference between consistent/inconsistent, STDDEV captures this intuition OK. However, in the future,
    # we may want to favor evidence for which hypotheses are inconsistent. Additionally, we may want to calculate
    # "marginal diagnosticity" which takes into the rest of the evidence.
    # (1) calculate the consensus for each hypothesis
    # (2) map N/A to neutral because N/A doesn't help determine consistency of the evidence
    # (3) calculate the population standard deviation of the evidence. It's more reasonable to consider the set of
    #     hypotheses at a given time to be the population of hypotheses than as a "sample" (although it doesn't matter
    #     much because we're comparing across hypothesis sets of the same size)
    na_neutral_consensuses = list(filter(None.__ne__, map(mean_na_neutral_vote, evaluations)))
    return statistics.pstdev(na_neutral_consensuses) if na_neutral_consensuses else 0.0


def detail(request, board_id, board_slug=None):
    """
    View the board details. Evidence is sorted in order of diagnosticity. Hypotheses are sorted in order of
    consistency.
    """
    def extract(x): return x.evidence.id, x.hypothesis.id

    view_type = request.GET.get('view_type')
    view_type = 'average' if view_type is None else view_type

    board = get_object_or_404(Board, pk=board_id)
    votes = Evaluation.objects.filter(board=board)

    participants = set(map(lambda x: x.user, votes))

    keyed = defaultdict(list)
    for vote in votes:
        keyed[extract(vote)].append(Eval.for_value(vote.value))
    consensus = {k: consensus_vote(v) for k, v in keyed.items()}
    disagreement = {k: calc_disagreement(v) for k, v in keyed.items()}

    user_votes = {extract(v): Eval.for_value(v.value) for v in votes.filter(user=request.user)} if request.user.is_authenticated else None

    # order evidence by diagnosticity and hypotheses by consistency
    hypotheses = list(board.hypothesis_set.all())
    evidence = list(board.evidence_set.all())

    hypothesis_consistency = list(
        map(lambda h: (h, inconsistency(
            map(lambda e: keyed[(e.id, h.id)], evidence)
        )), hypotheses))
    evidence_diagnosticity = list(
        map(lambda e: (e, diagnosticity(
            map(lambda h: keyed[(e.id, h.id)], hypotheses)
        )), evidence))

    evidence_diagnosticity.sort(key=lambda e: e[1], reverse=True)
    hypothesis_consistency.sort(key=lambda h: h[1])

    context = {
        'board': board,
        'evidences': evidence_diagnosticity,
        'hypotheses': hypothesis_consistency,
        'view_type': view_type,
        'votes': consensus,
        'user_votes': user_votes,
        'disagreement': disagreement,
        'participants': participants,
        'debug_stats': DEBUG
    }
    return render(request, 'boards/detail.html', context)


class BoardForm(forms.Form):
    board_title = forms.CharField(label='Board Title', max_length=200)
    board_desc = forms.CharField(label='Board Description', max_length=200, widget=forms.Textarea)
    hypothesis1 = forms.CharField(label='Hypothesis #1', max_length=200)
    hypothesis2 = forms.CharField(label='Hypothesis #2', max_length=200)


@login_required
def create_board(request):
    if request.method == 'POST':
        form = BoardForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                time = timezone.now()
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


class EvidenceForm(forms.Form):
    """
    Form to add a new piece of evidence. The evidence provided must have at least one source. The analyst can provide
    additional sources later.
    """
    evidence_desc = forms.CharField(
        label='Evidence', max_length=200,
        help_text='A short summary of the evidence. Use the Event Date field for capturing the date'
    )
    event_date = forms.DateField(
        label='Event Date',
        help_text='The date the event occurred or started',
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )
    evidence_url = forms.URLField(
        label='Source Website',
        help_text='A source (e.g., news article or press release) corroborating the evidence'
    )
    evidence_date = forms.DateField(
        label='Source Date',
        help_text='The date the source released or last updated the information corroborating the evidence. ' +
                  'Typically the date of the article or post',
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )


class EvidenceSourceForm(forms.Form):
    evidence_url = forms.URLField(
        label='Source Website',
        help_text='A source (e.g., news article or press release)',
    )
    evidence_date = forms.DateField(
        label='Source Date',
        help_text='The date the source released or last updated the information. ' +
                  'Typically the date of the article or post',
        widget=forms.DateInput(attrs={'class': "date", 'data-provide': 'datepicker'})
    )
    corroborating = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput()
    )


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


@login_required
def add_source(request, evidence_id):
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


@login_required
def add_source_tag(request, evidence_id, source_id):
    """Add a source tag for the given source and redirect to the evidence detail page for the associated evidence."""
    # May want to put in a sanity check here that source_id actually corresponds to evidence_id
    if request.method == 'POST':
        with transaction.atomic():
            source = get_object_or_404(EvidenceSource, pk=source_id)
            tag = EvidenceSourceTag.objects.get(tag_name=request.POST['tag'])
            # This assumes that each user can only add a tag once to a source
            AnalystSourceTag.objects.update_or_create(
                source=source,
                tagger=request.user,
                tag=tag,
                defaults={
                    'tag_date': timezone.now()
                }
            )
            messages.success(request, 'Added {} tag to source.'.format(tag.tag_name))
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
    else:
        raise Http404()


def evidence_detail(request, evidence_id):
    """Show detailed information about a piece of information and its sources"""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    available_tags = EvidenceSourceTag.objects.all()
    sources = EvidenceSource.objects.filter(evidence=evidence).order_by('-source_date')
    all_tags = AnalystSourceTag.objects.filter(source__in=sources)

    source_tags = defaultdict(list)
    for tag in all_tags:
        source_tags[(tag.source.id, tag.tag.id)].append(tag)

    context = {
        'evidence': evidence,
        'sources': sources,
        'source_tags': source_tags,
        'available_tags': available_tags,
    }
    return render(request, 'boards/evidence_detail.html', context)


class HypothesisForm(forms.Form):
    hypothesis_text = forms.CharField(label='Hypothesis', max_length=200)


@login_required
def add_hypothesis(request, board_id):
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


def profile(request, account_id=None):
    """
    Show the private/public profile for account_id. If account_id is None, shows the private profile for the logged in
    user. If account is specified and the user is not logged in, raise a 404.
    """
    if request.user and not account_id:
        account_id = request.user.id

    with transaction.atomic():
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
            'board_voted': voted
        }

    if request.user and request.user.id == account_id:
        return render(request, 'boards/profile.html', context)
    else:
        return render(request, 'boards/public_profile.html', context)


@login_required
def evaluate(request, board_id, evidence_id):
    """
    View for assessing a piece of evidence against all of the hypotheses. A couple measures are taken to attempt to
    reduce bias: (1) the analyst is not shown their previous assessment, and (2) the hypotheses are shown in a random
    order.
    """
    # TODO: fix the db transaction structure in this method
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


def robots(request):
    """Returns the robots.txt including the sitemap location (using the site domain)"""
    # Not sure if we should build the
    sitemap = ''.join(['https://', get_current_site(request).domain, reverse('django.contrib.sitemaps.views.sitemap')])
    return render(request, 'robots.txt', {'sitemap': sitemap}, content_type='text/plain')


def certbot(request, challenge_key):  # pragma: no cover
    """Respond to the Let's Encrypt certbot challenge"""
    # ignore coverage since keys aren't available in the testing environment
    if CERTBOT_PUBLIC_KEY and CERTBOT_PUBLIC_KEY == challenge_key:
        return HttpResponse(CERTBOT_SECRET_KEY)
    else:
        raise Http404()
