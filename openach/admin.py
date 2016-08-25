from django.contrib import admin
from .models import Board, Evidence, Hypothesis


class HypothesisInline(admin.StackedInline):
    model = Hypothesis
    extra = 2


class EvidenceInline(admin.StackedInline):
    model = Evidence
    extra = 2


class BoardAdmin(admin.ModelAdmin):
    inlines = [HypothesisInline, EvidenceInline]


admin.site.register(Board, BoardAdmin)


