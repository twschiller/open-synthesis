"""Analysis of Competing Hypotheses Board Metrics."""

import collections
import itertools
import logging
import statistics

from django.contrib.auth.models import AnonymousUser

from .models import Board, Eval, Evaluation, Evidence, Hypothesis
from .util import first_occurrences, partition

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def mean_na_neutral_vote(evaluations):
    """Return the mean rating on a 1-5 scale for the given evaluation, or None if there are no evaluations.

    Treats N/As as a neutral vote.
    """

    # NOTE: 'map' preferred to list comprehension here because the predicate is complicated
    def _replace_na(eval_):
        return (
            eval_.value
            if (eval_ and eval_ is not Eval.not_applicable)
            else Eval.neutral.value
        )

    return (
        statistics.mean(map(_replace_na, evaluations)) if evaluations else None
    )  # pylint: disable=bad-builtin


def calc_disagreement(evaluations):
    """Return the disagreement level for evaluations, or None if no evaluations.

    Calculated as the max disagreement of (1) N/A and non-N/A responses and (2) non-N/A evaluations
    :param evaluations: an iterable of Eval
    """
    if evaluations:
        na_it, rated_it = partition(lambda x: x is not Eval.not_applicable, evaluations)
        na_votes = list(na_it)
        rated_votes = list(rated_it)

        # Here we use the sample standard deviation because we consider the evaluations are a sample of all the
        # evaluations that could be given.
        # Not clear the best way to make the N/A disagreement comparable to the evaluation disagreement calculation
        na_disagreement = (
            statistics.stdev(([0] * len(na_votes)) + ([1] * len(rated_votes)))
            if len(na_votes) + len(rated_votes) > 1
            else 0.0
        )
        rated_disagreement = (
            statistics.stdev([v.value for v in rated_votes])
            if len(rated_votes) > 1
            else 0.0
        )
        return max(na_disagreement, rated_disagreement)
    else:
        return None


def aggregate_vote(evaluations):
    """Return the consensus evaluation given a an iterable of evaluations, or None if no evaluations.

    Calculated as (1) whether or not the evidence is applicable, and (2) if the evidence is applicable, how consistent
    the evidence is with the hypothesis. The calculation is conservative, rounding the result toward Eval.neutral
    if there is a tie.
    """
    na_it, rated_it = partition(Eval.not_applicable.__ne__, evaluations)
    na_votes = list(na_it)
    rated_votes = list(rated_it)

    if not na_votes and not rated_votes:
        return None
    elif len(na_votes) > len(rated_votes):
        return Eval.not_applicable
    else:
        consensus = round(statistics.mean([v.value for v in rated_votes]))
        return Eval(round(consensus))


def inconsistency(evaluations):
    """Return the inconsistency of a hypothesis with respect to a set of evidence.

    Calculation does not account for the reliability of the evidence (e.g., due to deception). Metric is monotonic in
    the number of pieces of evidence that have been evaluated. That is, for a given hypothesis, further evidence can
    only serve to refute it (though it may make the hypothesis more likely relative to the other hypotheses).
    :param evaluations: an iterable of iterables of Eval for a hypothesis
    """
    # The "inconsistency" needs to capture the extent to which a hypothesis has been refuted. The approach below
    # computes a metric similar to "sum squared error" for evidence where the consensus is that the hypotheses is
    # inconsistent. Currently we're treating N/A's a neutral. It may make sense to exclude them entirely because a
    # hypotheses can be considered more consistent just because there's less evidence that applies to it.
    # NOTE: could potentially speed up calculation be eliminating list comprehension before the sum
    na_neutral = map(mean_na_neutral_vote, evaluations)  # pylint: disable=bad-builtin
    return sum(
        (Eval.neutral.value - val) ** 2
        for val in na_neutral
        if val is not None and val < Eval.neutral.value
    )


def consistency(evaluations):
    """Return the consistency of a hypothesis with respect to a set of evidence. Ignore 'inconsistent' evaluations.

    Calculation does not account for the reliability of the evidence (e.g., due to deception).
    """
    na_neutral = map(mean_na_neutral_vote, evaluations)  # pylint: disable=bad-builtin
    return sum(
        (val - Eval.neutral.value) ** 2
        for val in na_neutral
        if val is not None and val > Eval.neutral.value
    )


def _proportion_value(evaluations, eval_):
    """Return proportion of evaluations where consensus is eval_."""
    consensuses = map(aggregate_vote, evaluations)  # pylint: disable=bad-builtin
    na, other = partition(eval_.__ne__, consensuses)
    na = list(na)
    other = list(other)
    total = len(na) + len(other)
    return len(na) / float(total) if total > 0 else 0.0


def proportion_na(evaluations):
    """Return the proportion of non-None evaluations that are N/A, or 0.0 if no evaluations."""
    return _proportion_value(evaluations, Eval.not_applicable)


def proportion_unevaluated(evaluations):
    """Return the proportion of missing evaluations."""
    return _proportion_value(evaluations, None)


def hypothesis_sort_key(evaluations):
    """Return a key for sorting hypotheses.

    Ordering is (1) inconsistency, (2) consistency, (3) proportion N/A, and (4) proportion unevaluated.
    """
    # could be made more efficient by not having to re-calculate mean_na_neutral and consensus vote
    return (
        inconsistency(evaluations),
        -consistency(evaluations),
        proportion_na(evaluations),
        proportion_unevaluated(evaluations),
    )


def diagnosticity(evaluations):
    """Return the diagnosticity of a piece of evidence given its evaluations against a set of hypotheses.

    :param evaluations: an iterable of iterables of Eval for a piece of evidence
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
    na_neutral = map(mean_na_neutral_vote, evaluations)  # pylint: disable=bad-builtin
    try:
        return statistics.pstdev(
            filter(None.__ne__, na_neutral)
        )  # pylint: disable=bad-builtin
    except statistics.StatisticsError:
        return 0.0


def evidence_sort_key(evaluations):
    """Return a key for sorting evidence.

    Ordering is (1) diagnosticity, (2) proportion N/A, and (3) proportion unevaluated.
    """
    # could be made more efficient by not having to re-calculate mean_na_neutral and consensus vote
    return (
        -diagnosticity(evaluations),
        proportion_na(evaluations),
        proportion_unevaluated(evaluations),
    )


def generate_contributor_count():
    """Return a dictionary mapping board ids to the contributor count.

    Contributors are people that either added a hypothesis or piece of evidence. This does not currently take into
    account people that modified the board.
    """
    contributor_count = collections.defaultdict(set)
    for evidence in Evidence.objects.all():
        contributor_count[evidence.board_id].add(evidence.creator_id)
    for hypothesis in Hypothesis.objects.all():
        contributor_count[hypothesis.board_id].add(hypothesis.creator_id)
    return {k: len(v) for k, v in contributor_count.items()}


def generate_evaluator_count():
    """Return a dictionary mapping board ids to the voter user ids.

    Does not consider whether or not the hypothesis or evidence has been removed.
    """
    voter_count = collections.defaultdict(set)
    for evaluation in Evaluation.objects.all():
        voter_count[evaluation.board_id].add(evaluation.user_id)
    return {k: len(v) for k, v in voter_count.items()}


def user_boards_created(user, viewing_user=AnonymousUser):
    """Return queryset of boards created by user in reverse creation order (most recently created first)."""
    return Board.objects.user_readable(viewing_user).filter(creator=user)


def user_boards_contributed(user, include_removed=False, viewing_user=AnonymousUser):
    """Return list of boards contributed to by the user in reverse order (most recent contributions first).

    :param user: the user
    :param include_removed: True iff boards that have been removed should be included in the result
    :param viewing_user: user for calculating permissions
    """

    # basic approach: (1) merge, (2) sort, and (3) add making sure there's no duplicate boards
    def _boards(class_):
        models = (
            class_.objects.filter(creator=user)
            .order_by("-submit_date")
            .select_related("board", "board__permissions")
        )
        return [
            (x.submit_date, x.board)
            for x in models
            if include_removed or not x.board.removed
        ]

    contributions = sorted(
        itertools.chain(_boards(Evidence), _boards(Hypothesis)),
        key=lambda x: x[0],
        reverse=True,
    )
    boards = [
        board
        for date, board in contributions
        if (include_removed or not board.removed) and board.can_read(viewing_user)
    ]
    return first_occurrences(boards)


def user_boards_evaluated(user, include_removed=False, viewing_user=AnonymousUser):
    """Return list of boards evaluated by user in reverse order of evaluation (most recently evaluated first).

    :param user: the user
    :param include_removed: True iff boards that have been removed should be included in the result
    :param viewing_user: user for calculating permissions
    """
    evaluations = Evaluation.objects.filter(user=user).order_by("-timestamp")
    boards = [
        e.board
        for e in evaluations.select_related("board", "board__permissions")
        if (include_removed or not e.board.removed) and e.board.can_read(viewing_user)
    ]
    return first_occurrences(boards)
