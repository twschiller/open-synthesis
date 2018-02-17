"""openach Admin Dashboard Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/ref/contrib/admin/
"""
from django.contrib import admin

from .models import Board, Evidence, Hypothesis, EvidenceSourceTag, ProjectNews, Team


class HypothesisInline(admin.StackedInline):
    """Inline editor for an ACH board's hypotheses."""

    model = Hypothesis
    extra = 2


class EvidenceInline(admin.StackedInline):
    """Inline editor for an ACH board's evidence."""

    model = Evidence
    extra = 2


class BoardAdmin(admin.ModelAdmin):
    """Admin interface for editing ACH boards."""

    inlines = [HypothesisInline, EvidenceInline]


admin.site.register(Board, BoardAdmin)
admin.site.register(EvidenceSourceTag)
admin.site.register(ProjectNews)
admin.site.register(Team)
