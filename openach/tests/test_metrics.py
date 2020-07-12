from django.test import TestCase

from openach.metrics import (
    aggregate_vote,
    calc_disagreement,
    consistency,
    diagnosticity,
    evidence_sort_key,
    hypothesis_sort_key,
    inconsistency,
    mean_na_neutral_vote,
    proportion_na,
    proportion_unevaluated,
)
from openach.models import Eval


class ConsensusTests(TestCase):
    def test_no_votes_has_no_consensus(self):
        """Test that aggregate_vote() returns None if no votes have been cast."""
        self.assertIsNone(aggregate_vote([]))

    def test_na_consensus_for_single_vote(self):
        """Test that aggregate_vote() returns N/A if only a single N/A vote is cast"""
        self.assertEqual(aggregate_vote([Eval.not_applicable]), Eval.not_applicable)

    def test_none_na_consensus_for_single_vote(self):
        """Test that aggregate_vote() returns the evaluation if only a single vote is cast."""
        self.assertEqual(aggregate_vote([Eval.consistent]), Eval.consistent)

    def test_equal_na_vs_non_na(self):
        """Test that consensus_vote() returns an evaluation when an equal number of N/A and non-N/A votes have been cast."""
        for vote in [Eval.very_inconsistent, Eval.neutral, Eval.very_consistent]:
            self.assertEqual(aggregate_vote([vote, Eval.not_applicable]), vote)
            self.assertEqual(aggregate_vote([Eval.not_applicable, vote]), vote)

    def test_round_toward_neutral(self):
        """Test that consensus_vote() rounds the vote toward a neutral assessment."""
        self.assertEqual(
            aggregate_vote([Eval.consistent, Eval.very_consistent]), Eval.consistent
        )
        self.assertEqual(
            aggregate_vote([Eval.inconsistent, Eval.very_inconsistent]),
            Eval.inconsistent,
        )


class EvidenceOrderingTests(TestCase):
    def test_mean_na_neutral_vote_maps_na_votes(self):
        """Test that mean_na_neutral_vote() maps N/A votes to neutral."""
        self.assertEqual(
            mean_na_neutral_vote([Eval.not_applicable]), Eval.neutral.value
        )
        self.assertEqual(
            mean_na_neutral_vote([Eval.not_applicable, Eval.very_inconsistent]),
            Eval.inconsistent.value,
        )

    def test_mean_na_neutral_vote_only_maps_na_votes(self):
        """Test that mean_na_neutral_vote() does not map values other than N/A."""
        for x in Eval:
            if x is not Eval.not_applicable:
                self.assertEqual(mean_na_neutral_vote([x]), x.value)

    def test_no_hypotheses_has_zero_diagnosticity(self):
        """Test that diagnosticity() returns 0.0 when there are no votes."""
        self.assertEqual(diagnosticity([]), 0.0)

    def test_no_votes_has_zero_diagnosticity(self):
        """Test that diagnosticity() returns 0.0 when there are no votes."""
        self.assertEqual(diagnosticity([[], []]), 0.0)

    def test_different_more_diagnostic_than_neutral(self):
        """Test that diagnosticity() is higher for hypothesis with different consensus."""
        different = diagnosticity([[Eval.consistent], [Eval.inconsistent]])
        same = diagnosticity([[Eval.neutral], [Eval.neutral]])
        self.assertGreater(different, same)

    def test_evidence_sorting(self):
        """Test evidence sorting."""
        evidence_reverse = [
            [[Eval.not_applicable], [Eval.not_applicable]],  # n/a: 1.0, none: 0.0
            [[Eval.not_applicable], []],  # n/a: 0.5, none: 0.5
            [[Eval.neutral], [Eval.not_applicable]],  # n/a: 0.5, none: 0.0
            [[], []],
            [[Eval.neutral], []],
            [[Eval.neutral], [Eval.neutral]],
            [[Eval.very_consistent], [Eval.very_inconsistent]],
        ]
        in_order = sorted(evidence_reverse, key=evidence_sort_key)
        evidence_reverse.reverse()  # reverse in place
        self.assertListEqual(in_order, evidence_reverse)


class HypothesisOrderingTests(TestCase):
    def test_no_evidence_has_zero_inconsistency(self):
        """Test that inconsistency() returns 0.0 when there is no evidence."""
        self.assertEqual(inconsistency([]), 0.0)

    def test_consistent_evidence_has_zero_inconsistency(self):
        """Test that inconsistency() returns 0.0 when a evaluation is neutral or more consistent."""
        for vote in [Eval.neutral, Eval.consistent, Eval.very_consistent]:
            self.assertEqual(inconsistency([[vote]]), 0.0)

    def test_inconsistent_evidence_has_nonzero_inconsistency(self):
        """Test that inconsistency() returns more than 0.0 when a evaluation is neutral or more consistent."""
        for vote in [Eval.very_inconsistent, Eval.inconsistent]:
            self.assertGreater(inconsistency([[vote]]), 0.0)

    def test_very_inconsistent_implies_more_inconsistent(self):
        """Test that inconsistency() returns a higher value for a hypothesis that has an inconsistent rating."""
        h1 = inconsistency([[Eval.consistent], [Eval.inconsistent]])
        h2 = inconsistency([[Eval.very_inconsistent], [Eval.inconsistent]])
        self.assertLess(h1, h2)

    def test_inconsistency_assumptions(self):
        """Test basic inconsistency() behavior.

        (1) a hypothesis with 3 inconsistent ratings is less consistent than a hypothesis with 2 inconsistent ratings,
        regardless of whether N/A or Neutral is one of the other ratings.

        (2) a hypothesis with a very inconsistent rating is more inconsistent than a hypothesis with not just
        inconsistent ratings
        """
        h1 = inconsistency(
            [
                [Eval.very_consistent],
                [Eval.not_applicable],
                [Eval.inconsistent],
                [Eval.inconsistent],
            ]
        )
        h2 = inconsistency(
            [
                [Eval.inconsistent],
                [Eval.inconsistent],
                [Eval.neutral],
                [Eval.inconsistent],
            ]
        )
        h3 = inconsistency(
            [
                [Eval.neutral],
                [Eval.not_applicable],
                [Eval.very_consistent],
                [Eval.very_inconsistent],
            ]
        )
        self.assertLess(h1, h2)
        self.assertLess(h2, h3)

    def test_calculate_na_proportion(self):
        """Test basic behavior of proportion_na()."""
        self.assertEqual(proportion_na([]), 0.0)
        self.assertEqual(proportion_na([[Eval.not_applicable]]), 1.0)
        self.assertEqual(proportion_na([[Eval.neutral]]), 0.0)
        self.assertEqual(
            proportion_na([[Eval.not_applicable], [Eval.not_applicable]]), 1.0
        )
        self.assertEqual(proportion_na([[Eval.not_applicable], []]), 0.5)
        self.assertEqual(proportion_na([[Eval.neutral], [Eval.not_applicable]]), 0.5)

    def test_calculate_unevaluated_proportion(self):
        """Test basic behavior of proportion_unevaluated()."""
        self.assertEqual(proportion_unevaluated([]), 0.0)
        self.assertEqual(proportion_unevaluated([[]]), 1.0)
        self.assertEqual(proportion_unevaluated([[Eval.not_applicable]]), 0.0)
        self.assertEqual(proportion_unevaluated([[]]), 1.0)
        self.assertEqual(proportion_unevaluated([[], [Eval.not_applicable]]), 0.5)

    def test_calculate_consistency(self):
        """Test basic behavior of consistency()."""
        self.assertEqual(consistency([]), 0.0)
        self.assertGreater(
            consistency([[Eval.very_consistent]]), consistency([[Eval.consistent]])
        )

    def test_hypothesis_sorting(self):
        """Test that we can sort hypotheses."""
        hypotheses_reverse = [
            [[Eval.very_inconsistent]],
            [[Eval.inconsistent]],
            [[Eval.not_applicable]],
            [[]],
            [[Eval.neutral]],
            [[Eval.consistent]],
            [[Eval.very_consistent]],
        ]
        in_order = sorted(hypotheses_reverse, key=hypothesis_sort_key)
        hypotheses_reverse.reverse()  # reverse in place
        self.assertListEqual(in_order, hypotheses_reverse)


class DisagreementTests(TestCase):
    def test_no_votes_returns_none(self):
        """Test that calc_disagreement() returns None when there is no votes"""
        self.assertEqual(calc_disagreement([]), None)

    def test_single_vote_has_zero_disagreement(self):
        """Test that calc_disagreement() returns 0.0 when there is a single vote."""
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote]), 0.0)

    def test_same_vote_has_zero_disagreement(self):
        """Test that calc_disagreement() returns 0.0 when there are only votes of a single type."""
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote, vote]), 0.0)

    def test_extreme_votes_have_greater_disagreement(self):
        """Test that votes that are further from neutral result in a larger disagreement score."""
        small = [Eval.consistent, Eval.inconsistent]
        large = [Eval.very_inconsistent, Eval.very_consistent]
        self.assertGreater(calc_disagreement(large), calc_disagreement(small))
