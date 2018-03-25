"""Analysis of Competing Hypotheses Django Application Forms.

For more information, please see:
    - https://docs.djangoproject.com/en/1.10/topics/forms/
    - https://docs.djangoproject.com/en/1.10/topics/forms/modelforms/
"""

from django import forms
from django.forms import ValidationError
from django.utils.translation import ugettext_lazy as _

from .models import User, Board, BoardPermissions, Evidence, EvidenceSource, Hypothesis, UserSettings, Team, TeamRequest
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


class BoardPermissionForm(forms.ModelForm):
    """Form for setting/modifying board permissions."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Form meta options."""

        model = BoardPermissions
        fields = ['read_board', 'read_comments', 'add_comments', 'add_elements', 'edit_elements', 'edit_board', 'collaborators', 'teams']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # NOTE: a user who doesn't have access to a team can see the team name here if it's already a collaborator
        # on the board. In the future, might want to hide those team names here
        team_ids = set(Team.objects.user_visible(user=user).values_list('id', flat=True)) | set(kwargs['instance'].teams.values_list('id', flat=True))
        self.fields['teams'].queryset = Team.objects.filter(id__in=team_ids)
        self.fields['collaborators'].label = _('User Collaborators')
        self.fields['teams'].label = _('Team Collaborators')


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


class TeamCreateForm(forms.ModelForm):
    """Form for creating/editing a new team."""

    class Meta:
        model = Team
        fields = ['name', 'description', 'url', 'public', 'invitation_required']


class TeamInviteForm(forms.Form):
    """Form for creating/editing a new team."""

    members = forms.ModelMultipleChoiceField(User.objects.all())

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)

        member_ids = set(team.members.values_list('id', flat=True))
        pending_ids = set(TeamRequest.objects.filter(team=team).values_list('invitee', flat=True))
        self.fields['members'].queryset = User.objects.exclude(pk__in=member_ids | pending_ids).order_by('username')
