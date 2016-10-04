"""Analysis of Competing Hypotheses Django Application Forms.

For more information, please see:
    - https://docs.djangoproject.com/en/1.10/topics/forms/
    - https://docs.djangoproject.com/en/1.10/topics/forms/modelforms/
"""

from django import forms
from django.forms import ValidationError
from django.utils.translation import ugettext_lazy as _

from .models import Board, Evidence, EvidenceSource, Hypothesis, UserSettings
from .models import HYPOTHESIS_MAX_LENGTH


class BoardForm(forms.ModelForm):
    """Board form."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = Board
        fields = ['board_title', 'board_desc']
        widgets = {
            'board_desc': forms.Textarea(attrs={'rows': 2})
        }


class BoardCreateForm(BoardForm):
    """Board creation form where creator must specify two competing hypotheses."""

    hypothesis1 = forms.CharField(
        label=_('Hypothesis #1'),
        max_length=HYPOTHESIS_MAX_LENGTH,
        help_text=_('A hypothesis providing a potential answer to the topic question')
    )
    hypothesis2 = forms.CharField(
        label=_('Hypothesis #2'),
        max_length=HYPOTHESIS_MAX_LENGTH,
        help_text=_('An alternative hypothesis providing a potential answer to the topic question')
    )


class EvidenceForm(forms.ModelForm):
    """Form for modifying the basic evidence information."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = Evidence
        fields = ['evidence_desc', 'event_date']
        widgets = {
            'event_date': forms.DateInput(attrs={'class': 'date', 'data-provide': 'datepicker'})
        }


class EvidenceSourceForm(forms.ModelForm):
    """Form for adding a source to a piece of evidence."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = EvidenceSource
        fields = ['source_url', 'source_date', 'corroborating']
        widgets = {
            'source_date': forms.DateInput(attrs={'class': 'date', 'data-provide': 'datepicker'}),
            'corroborating': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        """Initializer that can mark the fields as optional.

        Currently the only time to mark the fields as optional is when allowing the user to add a source when
        adding a piece of evidence.

        :param require: whether or not the source_url and source_date fields should be required
        """
        require = kwargs.pop('require', True)
        super(EvidenceSourceForm, self).__init__(*args, **kwargs)
        if not require:
            for field_name in ['source_url', 'source_date']:
                field = self.fields[field_name]
                field.required = False
                field.label += ' (Optional)'

    def clean(self):
        """Validate that a date is provided if a URL is provided."""
        cleaned_data = super(EvidenceSourceForm, self).clean()
        if cleaned_data.get('evidence_url') and not cleaned_data.get('evidence_date'):
            raise ValidationError(_('Provide a date for the source.'), code='invalid')


class HypothesisForm(forms.ModelForm):
    """Form for a board hypothesis."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = Hypothesis
        fields = ['hypothesis_text']


class SettingsForm(forms.ModelForm):
    """User account settings form."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = UserSettings
        fields = ['digest_frequency']
