"""Analysis of Competing Hypotheses Django Application Model Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/topics/db/models/
"""
import datetime
import logging
from enum import Enum, unique

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
# NOTE: django.core.urlresolvers was deprecated in Django 1.10. Landscape is loading version 1.9.9 for some reason
from django.urls import reverse, NoReverseMatch  # pylint: disable=no-name-in-module
from django.conf import settings
from field_history.tracker import FieldHistoryTracker


# See database portability constraints here: https://docs.djangoproject.com/en/1.10/ref/databases/#character-fields
URL_MAX_LENGTH = 255
EVIDENCE_MAX_LENGTH = 200
HYPOTHESIS_MAX_LENGTH = 200
BOARD_TITLE_MAX_LENGTH = 200
BOARD_DESC_MAX_LENGTH = 255

SLUG_MAX_LENGTH = getattr(settings, 'SLUG_MAX_LENGTH', 72)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Board(models.Model):
    """An ACH matrix with hypotheses, evidence, and evaluations."""

    board_title = models.CharField(max_length=BOARD_TITLE_MAX_LENGTH)
    board_slug = models.SlugField(null=True, allow_unicode=False, max_length=SLUG_MAX_LENGTH)
    board_desc = models.CharField('board description', max_length=BOARD_DESC_MAX_LENGTH)
    creator = models.ForeignKey(User, null=True)
    pub_date = models.DateTimeField('date published')
    field_history = FieldHistoryTracker(['board_title', 'board_desc'])

    def __str__(self):
        """Return a human-readable representation of the board."""
        return self.board_title

    def was_published_recently(self):
        """Return True iff the Board was created recently."""
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now

    def get_absolute_url(self):
        """Return the absolute URL for viewing the board details, including the slug."""
        if self.board_slug:
            try:
                return reverse('openach:detail_slug', args=(self.id, self.board_slug,))
            except NoReverseMatch:
                logger.warning("Malformed SLUG for reverse URL match: %s", self.board_slug)
                return reverse('openach:detail', args=(self.id,))
        else:
            return reverse('openach:detail', args=(self.id,))


class Hypothesis(models.Model):
    """An ACH matrix hypothesis."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    hypothesis_text = models.CharField('hypothesis', max_length=HYPOTHESIS_MAX_LENGTH)
    creator = models.ForeignKey(User, null=True)
    submit_date = models.DateTimeField('date added')
    field_history = FieldHistoryTracker(['hypothesis_text'])

    class Meta:  # pylint: disable=too-few-public-methods
        """Hypothesis Model meta options.

        For more information, please see:
            https://docs.djangoproject.com/en/1.10/topics/db/models/#meta-options
        """

        verbose_name_plural = "hypotheses"

    def __str__(self):
        """Return a human-readable representation of the hypothesis."""
        return self.hypothesis_text


class Evidence(models.Model):
    """A piece of evidence for an ACH matrix."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    creator = models.ForeignKey(User, null=True)
    evidence_desc = models.CharField('evidence description', max_length=EVIDENCE_MAX_LENGTH)
    event_date = models.DateField('evidence event date', null=True)
    submit_date = models.DateTimeField('date added')
    field_history = FieldHistoryTracker(['evidence_desc', 'event_date'])

    class Meta:  # pylint: disable=too-few-public-methods
        """Evidence Model meta options.

        For more information, please see:
            https://docs.djangoproject.com/en/1.10/topics/db/models/#meta-options
        """

        verbose_name_plural = "evidence"


class EvidenceSource(models.Model):
    """A source for a piece of evidence in the ACH matrix."""

    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE)
    source_url = models.URLField(max_length=URL_MAX_LENGTH)
    # the date the source was last updated/released
    source_date = models.DateField('source date')
    uploader = models.ForeignKey(User)
    submit_date = models.DateTimeField('date added')
    corroborating = models.BooleanField()


class EvidenceSourceTag(models.Model):
    """A tag that an analyst can apply to an evidence source."""

    tag_name = models.CharField(max_length=64, unique=True)
    tag_desc = models.CharField(max_length=200)

    def __str__(self):
        """Return a human-readable representation of the source tag."""
        return "{}: {}".format(self.tag_name, self.tag_desc)


class AnalystSourceTag(models.Model):
    """An instance of an analyst tagging an evidence source with a tag."""

    source = models.ForeignKey(EvidenceSource, on_delete=models.CASCADE)
    tagger = models.ForeignKey(User, on_delete=models.CASCADE)
    tag = models.ForeignKey(EvidenceSourceTag, on_delete=models.CASCADE)
    tag_date = models.DateTimeField('date tagged')


@unique
class Eval(Enum):
    """Possible choices for evaluating a hypothesis with respect to a piece of evidence."""

    not_applicable = 0
    very_inconsistent = 1
    inconsistent = 2
    neutral = 3
    consistent = 4
    very_consistent = 5

    @staticmethod
    def for_value(val):
        """Return the Enum entry associated with val, or None."""
        return next(e for e in Eval if e.value == val)


class Evaluation(models.Model):
    """A user's evaluation of a hypothesis with respect to a piece of evidence."""

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
        """Return a human-readable representation of the evaluation."""
        # NOTE: Django's ORM automatically generates a get_xxx_display() member variable
        return self.get_value_display()  # pylint: disable=no-member


class ProjectNews(models.Model):
    """A news alert for the front page."""

    content = models.CharField(max_length=1024)
    pub_date = models.DateTimeField('date published')
    author = models.ForeignKey(User, null=True)
