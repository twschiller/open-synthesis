from django.template.defaulttags import register
from openach.models import Evaluation


@register.simple_tag
def get_detail(dictionary, evidence_id, hypothesis_id):
    """Returns the evaluation detail for a given hypothesis and piece of evidence"""
    value = dictionary.get((evidence_id, hypothesis_id))
    if eval:
        return next(e[1] for e in Evaluation.EVALUATION_OPTIONS if e[0] == value.value)
    else:
        return None


