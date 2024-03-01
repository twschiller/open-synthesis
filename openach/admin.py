"""openach Admin Dashboard Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/ref/contrib/admin/
"""
from django.contrib import admin

from . import forms
from .models import Board, Evidence, EvidenceSourceTag, Hypothesis, ProjectNews, Team, Invitation, UserSettings


class HypothesisInline(admin.StackedInline):
    """Inline editor for an ACH board's hypotheses."""

    model = Hypothesis
    extra = 2


class EvidenceInline(admin.StackedInline):
    """Inline editor for an ACH board's evidence."""

    model = Evidence
    extra = 2


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    """Admin interface for editing ACH boards."""

    inlines = [HypothesisInline, EvidenceInline]


class InvitationInline(admin.TabularInline):
    model = Invitation
    fields = ['invitee_email', 'accepted', 'created_at']
    readonly_fields = ['created_at']
    extra = 0  # Prevents adding new invites directly here


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    """Admin interface for allocating invites for users."""
    inlines = [InvitationInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['invites_remaining'].widget = forms.TextInput()  # Customize
        return form


admin.site.register(EvidenceSourceTag)
admin.site.register(ProjectNews)
admin.site.register(Team)
