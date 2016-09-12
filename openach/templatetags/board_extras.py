"""openach Django Template Helper Methods

For more information, please see:
    https://docs.djangoproject.com/en/1.10/howto/custom-template-tags/
"""
import logging
import collections
import math

from django.template.defaulttags import register

from openach.models import Evaluation, Eval


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@register.simple_tag
def get_detail(dictionary, evidence_id, hypothesis_id):
    """Returns the evaluation Eval for a given hypothesis and piece of evidence"""
    return dictionary.get((evidence_id, hypothesis_id))


@register.filter
def detail_name(eval_):
    """Returns the human-readable name for the given evaluation"""
    if eval_:
        return next(e[1] for e in Evaluation.EVALUATION_OPTIONS if e[0] == eval_.value)
    else:
        return 'No Assessments'


@register.filter
def detail_classname(eval_):
    """Returns the CSS style associate with the given evaluation"""
    mapping = {
        None: "eval-no-assessments",
        Eval.consistent: "eval-consistent",
        Eval.inconsistent: "eval-inconsistent",
        Eval.very_inconsistent: "eval-very-inconsistent",
        Eval.very_consistent: "eval-very-consistent",
        Eval.not_applicable: "eval-not-applicable",
        Eval.neutral: "eval-neutral"
    }
    result = mapping.get(eval_)
    return result


@register.simple_tag
def get_source_tags(dictionary, source_id, tag_id):
    """Performs a dictionary lookup, returning None if the key is not in the dictionary"""
    return dictionary.get((source_id, tag_id))


DisputeLevel = collections.namedtuple('DisputeLevel', ['max_level', 'name', 'css_class'])
DISPUTE_LEVELS = [
    DisputeLevel(max_level=0.5, name='Consensus', css_class='disagree-consensus'),
    DisputeLevel(max_level=1.5, name='Mild Dispute', css_class='disagree-mild-dispute'),
    DisputeLevel(max_level=2.0, name='Large Dispute', css_class='disagree-large-dispute'),
    DisputeLevel(max_level=math.inf, name='Extreme Dispute', css_class='disagree-extreme-dispute'),
]


def _dispute_level(value):
    return list(filter(lambda x: value < x.max_level, DISPUTE_LEVELS))[0]


@register.filter
def disagreement_category(value):
    """Returns a human-readable description of the level of disagreement given by the value"""
    return 'No Assessments' if value is None else _dispute_level(value).name


@register.filter
def disagreement_style(value):
    """Returns the CSS class name associated with the given level of disagreement"""
    return 'disagree-no-assessments' if value is None else _dispute_level(value).css_class


@register.simple_tag
def comparison_style(user, consensus):
    """
    Returns the CSS style for the analysis cell given a user evaluation and the consensus evaluation. Assumes that the
    user disagrees with the consensus. If user roughly agrees, shows the weak consistent/inconsistent style. Otherwise,
    returns the dispute style depending on distance between evaluations.
    """
    assert user != consensus
    diff = abs(user.value - consensus.value)
    non_na = user.value > 0 and consensus.value > 0

    if non_na and user.value < 3 and consensus.value < 3:
        return 'eval-inconsistent'
    elif non_na and user.value > 3 and consensus.value > 3:
        return 'eval-consistent'
    elif user.value == 0 or consensus.value == 0:
        return 'disagree-mild-dispute'
    elif diff >= 3:
        return 'disagree-extreme-dispute'
    elif diff >= 2:
        return 'disagree-large-dispute'
    elif diff >= 1:
        return 'disagree-mild-dispute'
    else:
        return 'disagree-consensus'


@register.filter
def bootstrap_alert(tags):
    """
    If value is a Django message level, returns the corresponding bootstrap alert css class. Assumes a single tag
    for the message. See https://docs.djangoproject.com/en/1.10/ref/contrib/messages/#message-tags
    """
    mapping = {
        'debug': 'alert-info',
        'info': 'alert-info',
        'success': 'alert-success',
        'warning': 'alert-warning',
        'error': 'alert-error',
    }
    return mapping[tags] if tags in mapping else tags


@register.filter
def board_url(board):
    """Return the URL for the board, including the slug if available."""
    # In the future, we might just want to directly use get_absolute_url in the template. However, this extra level
    # of indirection gives us some additional flexibility
    return board.get_absolute_url()


@register.simple_tag
def get_verbose_field_name(instance, field_name):
    """Returns verbose name for a field"""
    # https://stackoverflow.com/questions/14496978/fields-verbose-name-in-templates
    # _meta is a standard API in Django: https://docs.djangoproject.com/en/1.10/ref/models/meta/
    return instance._meta.get_field(field_name).verbose_name.title()  # pylint: disable=protected-access
