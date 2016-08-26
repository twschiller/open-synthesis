from django.db import models
import datetime
from django.utils import timezone
from django.contrib.auth.models import User
from enum import Enum, unique


class Board(models.Model):
    """An ACH matrix with hypotheses, evidence, and evaluations."""
    board_title = models.CharField(max_length=200)
    board_desc = models.CharField(max_length=200)
    creator = models.ForeignKey(User, null=True)
    pub_date = models.DateTimeField('date published')

    def __str__(self):
        return self.board_title

    def was_published_recently(self):
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now


class Hypothesis(models.Model):
    """An ACH matrix hypothesis."""
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    hypothesis_text = models.CharField(max_length=200)
    creator = models.ForeignKey(User, null=True)

    def __str__(self):
        return self.hypothesis_text


class Evidence(models.Model):
    """A piece of evidence for an ACH matrix."""
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    creator = models.ForeignKey(User, null=True)
    evidence_desc = models.CharField(max_length=200)
    evidence_url = models.URLField()


@unique
class Eval(Enum):
    """Possible choices for evaluating a hypothesis w.r.t. a piece of evidence"""
    not_applicable = 0
    very_inconsistent = 1
    inconsistent = 2
    neutral = 3
    consistent = 4
    very_consistent = 5

    @staticmethod
    def for_value(val):
        """Returns the Enum entry associated with val, or None"""
        return next(e for e in Eval if e.value == val)


class Evaluation(models.Model):
    """A user's evaluation of a hypothesis w.r.t. a piece of evidence."""
    EVALUATION_OPTIONS = (
        (Eval.not_applicable.value, 'N/A'),
        (Eval.very_inconsistent.value, 'Very Inconsistent'),
        (Eval.inconsistent.value, 'Inconsistent'),
        (Eval.neutral.value, 'Neutral'),
        (Eval.consistent.value, 'Consistent'),
        (Eval.very_consistent.value, 'Very Consistent'),
    )
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    hypothesis = models.ForeignKey(Hypothesis, on_delete=models.CASCADE)
    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    value = models.PositiveSmallIntegerField(default=0, choices=EVALUATION_OPTIONS)

    def __str__(self):
        return self.get_value_display()
