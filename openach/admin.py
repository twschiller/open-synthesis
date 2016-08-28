from django.contrib import admin
from .models import Board, Evidence, Hypothesis, EvidenceSourceTag, ProjectNews


class HypothesisInline(admin.StackedInline):
    model = Hypothesis
    extra = 2


class EvidenceInline(admin.StackedInline):
    model = Evidence
    extra = 2


class BoardAdmin(admin.ModelAdmin):
    inlines = [HypothesisInline, EvidenceInline]


admin.site.register(Board, BoardAdmin)
admin.site.register(EvidenceSourceTag)
admin.site.register(ProjectNews)
