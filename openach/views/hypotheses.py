import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from openach.auth import check_edit_authorization
from openach.forms import HypothesisForm
from openach.models import Board, Hypothesis
from openach.models import BoardFollower

from .notifications import notify_edit, notify_add
from .util import remove_and_redirect

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def add_hypothesis(request, board_id):
    """Return a view for adding a hypothesis, or handle form submission."""
    board = get_object_or_404(Board, pk=board_id)
    existing = Hypothesis.objects.filter(board=board)

    if 'add_elements' not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            hypothesis = form.save(commit=False)
            hypothesis.board = board
            hypothesis.creator = request.user
            hypothesis.save()
            BoardFollower.objects.update_or_create(board=board, user=request.user, defaults={
                'is_contributor': True,
            })
            notify_add(board, actor=request.user, action_object=hypothesis)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm()

    context = {
        'form': form,
        'board': board,
        'hypotheses': existing,
    }
    return render(request, 'boards/add_hypothesis.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def edit_hypothesis(request, hypothesis_id):
    """Return a view for editing a hypothesis, or handle board submission."""
    hypothesis = get_object_or_404(Hypothesis, pk=hypothesis_id)
    # don't care if the board has been removed
    board = hypothesis.board
    check_edit_authorization(request, board, hypothesis)

    if request.method == 'POST':
        form = HypothesisForm(request.POST, instance=hypothesis)
        if 'remove' in form.data:
            return remove_and_redirect(request, hypothesis, hypothesis.hypothesis_text)

        elif form.is_valid():
            form.save()
            messages.success(request, _('Updated hypothesis: {text}').format(text=form.cleaned_data['hypothesis_text']))  # nopep8
            notify_edit(board, actor=request.user, action_object=hypothesis)
            return HttpResponseRedirect(reverse('openach:detail', args=(board.id,)))
    else:
        form = HypothesisForm(instance=hypothesis)

    context = {
        'form': form,
        'hypothesis': hypothesis,
        'board': board,
        'allow_remove': getattr(settings, 'EDIT_REMOVE_ENABLED', True),
    }

    return render(request, 'boards/edit_hypothesis.html', context)
