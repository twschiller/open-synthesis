from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from .models import Board, Hypothesis, Evidence, Evaluation, Eval
from collections import defaultdict
from django.db import transaction
import logging, itertools
from django.urls import reverse
import statistics
from django import forms
from django.utils import timezone

logger = logging.getLogger(__name__)


def index(request):
    latest_board_list = Board.objects.order_by('-pub_date')[:5]
    context = {
        'latest_board_list': latest_board_list,
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


def consensus_vote(evaluations):
    """
    Determine the consensus Eval given an iterable of Eval. (1) whether or not the evidence is applicable, and
    (2) if the evidence is applicable, how consistent the evidence is with the hypothesis. Is conservative, adjusting
    the result toward neutral if there is a "tie".
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


def detail(request, board_id):
    def extract(x): return x.evidence.id, x.hypothesis.id

    board = get_object_or_404(Board, pk=board_id)
    votes = Evaluation.objects.filter(board=board)

    keyed = defaultdict(list)
    for vote in votes:
        keyed[extract(vote)].append(Eval.for_value(vote.value))
    consensus = {k: consensus_vote(v) for k, v in keyed.items()}

    context = {
        'board': board,
        'votes': consensus
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
                board = Board.objects.create(
                    board_title=form.cleaned_data['board_title'],
                    board_desc=form.cleaned_data['board_desc'],
                    creator=request.user,
                    pub_date=timezone.now()
                )
                for hypothesis_key in ['hypothesis1', 'hypothesis2']:
                    Hypothesis.objects.create(
                        board=board,
                        hypothesis_text=form.cleaned_data[hypothesis_key]
                    )

            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = BoardForm()
    return render(request, 'boards/create_board.html', {'form': form})


class EvidenceForm(forms.Form):
    evidence_desc = forms.CharField(label='Evidence', max_length=200)
    evidence_url = forms.URLField()


@login_required
def add_evidence(request, board_id):
    board = get_object_or_404(Board, pk=board_id)

    if request.method == 'POST':
        form = EvidenceForm(request.POST)
        if form.is_valid():
            Evidence.objects.create(
                evidence_desc=form.cleaned_data['evidence_desc'],
                evidence_url=form.cleaned_data['evidence_url'],
                board=board,
                creator=request.user
            )
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = EvidenceForm()
    return render(request, 'boards/add_evidence.html', {'form': form, 'board': board})


class HypothesisForm(forms.Form):
    hypothesis_text = forms.CharField(label='Hypothesis', max_length=200)


@login_required
def add_hypothesis(request, board_id):
    board = get_object_or_404(Board, pk=board_id)
    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            Hypothesis.objects.create(
                hypothesis_text=form.cleaned_data['hypothesis_text'],
                board=board,
                creator=request.user
            )
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm()
    return render(request, 'boards/add_hypothesis.html', {'form': form, 'board': board})


@login_required
def profile(request):
    return render(request, 'boards/profile.html')


@login_required
def evaluate(request, board_id, evidence_id):

    # TODO: fix the db transaction structure in this method

    board = get_object_or_404(Board, pk=board_id)
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    hypotheses = Hypothesis.objects.filter(board=board_id)

    if request.method == 'GET':
        context = {
            'board': board,
            'evidence': evidence,
            'hypotheses': hypotheses,
            'options': Evaluation.EVALUATION_OPTIONS
        }
        return render(request, 'boards/evaluate.html', context)

    elif request.method == 'POST':
        with transaction.atomic():
            # Remove user's previous votes for the the piece of evidence
            Evaluation.objects.filter(board=board_id, evidence=evidence_id, user=request.user).delete()

            # Add new votes for the hypotheses
            for hypothesis in hypotheses:
                select = request.POST['hypothesis-{}'.format(hypothesis.id)]
                Evaluation.objects.create(
                    board=board,
                    evidence=evidence,
                    hypothesis=hypothesis,
                    user=request.user,
                    value=select
                )

        return HttpResponseRedirect(reverse('openach:detail', args=(board_id,)))
    else:
        raise Http404()

