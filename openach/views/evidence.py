from collections import defaultdict
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_http_methods, require_safe

from openach.auth import check_edit_authorization
from openach.decorators import cache_if_anon, account_required
from openach.forms import EvidenceForm, EvidenceSourceForm
from openach.models import Board, Evidence, EvidenceSource, AnalystSourceTag, EvidenceSourceTag
from openach.models import BoardFollower
from openach.tasks import fetch_source_metadata

from .util import remove_and_redirect
from .notifications import notify_add, notify_edit

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, 'PAGE_CACHE_TIMEOUT_SECONDS', 60)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def evidence_detail(request, evidence_id):
    """Return a view displaying detailed information about a piece of evidence and its sources."""
    # NOTE: cannot cache page for logged in users b/c comments section contains CSRF and other protection mechanisms.
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    available_tags = EvidenceSourceTag.objects.all()
    sources = EvidenceSource.objects.filter(evidence=evidence).order_by('-source_date').select_related('uploader')
    all_tags = AnalystSourceTag.objects.filter(source__in=sources)

    source_tags = defaultdict(list)
    user_tags = defaultdict(list)
    for tag in all_tags:
        key = (tag.source_id, tag.tag_id)
        source_tags[key].append(tag)
        if tag.tagger_id == request.user.id:
            user_tags[key].append(tag)

    context = {
        'evidence': evidence,
        'sources': sources,
        'source_tags': source_tags,
        'user_tags': user_tags,
        'available_tags': available_tags,
        'meta_description': _("Analysis of evidence: {description}").format(description=evidence.evidence_desc)
    }
    return render(request, 'boards/evidence_detail.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_evidence(request, board_id):
    """Return a view of adding evidence (with a source), or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if 'add_elements' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    require_source = getattr(settings, 'EVIDENCE_REQUIRE_SOURCE', True)

    if request.method == 'POST':
        evidence_form = EvidenceForm(request.POST)
        source_form = EvidenceSourceForm(request.POST)
        if evidence_form.is_valid() and source_form.is_valid():
            with transaction.atomic():
                evidence = evidence_form.save(commit=False)
                evidence.board = board
                evidence.creator = request.user
                evidence.save()

                if source_form.cleaned_data.get('source_url'):
                    source = source_form.save(commit=False)
                    source.evidence = evidence
                    source.uploader = request.user
                    source.save()
                    fetch_source_metadata.delay(source.id)

                BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                    'is_contributor': True,
                })
            notify_add(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        evidence_form = EvidenceForm()
        source_form = EvidenceSourceForm(require=require_source, initial={'corroborating': True})

    context = {
        'board': board,
        'evidence_form': evidence_form,
        'source_form': source_form,
    }
    return render(request, 'boards/add_evidence.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_evidence(request, evidence_id):
    """Return a view for editing a piece of evidence, or handle for submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    # don't care that the board might have been removed
    board = evidence.board
    check_edit_authorization(request, board=board, has_creator=evidence)

    if request.method == 'POST':
        form = EvidenceForm(request.POST, instance=evidence)
        if 'remove' in form.data:
            return remove_and_redirect(request, evidence, evidence.evidence_desc)

        elif form.is_valid():
            form.save()
            messages.success(request, _('Updated evidence description and date.'))
            notify_edit(board, actor=request.user, action_object=evidence)
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence.id,)))

    else:
        form = EvidenceForm(instance=evidence)

    context = {
        'form': form,
        'evidence': evidence,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_evidence.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_source(request, evidence_id):
    """Return a view for adding a corroborating/contradicting source, or handle form submission."""
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    if request.method == 'POST':
        form = EvidenceSourceForm(request.POST)
        if form.is_valid():
            source = form.save(commit=False)
            source.evidence = evidence
            source.uploader = request.user
            source.save()
            fetch_source_metadata.delay(source.id)
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
        else:
            corroborating = form.data['corroborating'] == 'True'
    else:
        corroborating = request.GET.get('kind') is None or request.GET.get('kind') != 'conflicting'
        form = EvidenceSourceForm(initial={'corroborating': corroborating})

    context = {
        'form': form,
        'evidence': evidence,
        'corroborating': corroborating
    }

    return render(request, 'boards/add_source.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def toggle_source_tag(request, evidence_id, source_id):
    """Toggle source tag for the given source and redirect to the evidence detail page for the associated evidence."""
    # May want to put in a sanity check here that source_id actually corresponds to evidence_id
    # Inefficient to have to do the DB lookup before making a modification. May want to have the client pass in
    # whether or not they're adding/removing the tag
    if request.method == 'POST':
        with transaction.atomic():
            source = get_object_or_404(EvidenceSource, pk=source_id)
            tag = EvidenceSourceTag.objects.get(tag_name=request.POST['tag'])
            user_tag = AnalystSourceTag.objects.filter(source=source, tagger=request.user, tag=tag)
            if user_tag.count() > 0:
                user_tag.delete()
                messages.success(request, _('Removed "{name}" tag from source.').format(name=tag.tag_name))
            else:
                AnalystSourceTag.objects.create(source=source, tagger=request.user, tag=tag)
                messages.success(request, _('Added "{name}" tag to source.').format(name=tag.tag_name))
            return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
    else:
        # Redirect to the form where the user can toggle a source tag
        return HttpResponseRedirect(reverse('openach:evidence_detail', args=(evidence_id,)))
