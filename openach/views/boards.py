import itertools
import json
import logging
import random
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe
from field_history.models import FieldHistory

from openach.decorators import account_required, cache_if_anon, cache_on_auth
from openach.forms import BoardCreateForm, BoardForm, BoardPermissionForm
from openach.metrics import (
    aggregate_vote,
    calc_disagreement,
    evidence_sort_key,
    generate_contributor_count,
    generate_evaluator_count,
    hypothesis_sort_key,
    user_boards_contributed,
    user_boards_created,
    user_boards_evaluated,
)
from openach.models import Board, BoardFollower, Eval, Evaluation, Evidence, Hypothesis

from .util import make_paginator

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

BOARD_SEARCH_RESULTS_MAX = getattr(settings, "BOARD_SEARCH_RESULTS_MAX", 5)
PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, "PAGE_CACHE_TIMEOUT_SECONDS", 60)
DEBUG = getattr(settings, "DEBUG", False)


@require_safe
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
@account_required
def board_listing(request):
    """Return a paginated board listing view showing all boards and their popularity."""
    board_list = Board.objects.user_readable(request.user).order_by("-pub_date")
    metric_timeout_seconds = 60 * 2
    desc = _("List of intelligence boards on {name} and summary information").format(
        name=get_current_site(request).name
    )  # nopep8
    return render(
        request,
        "boards/boards.html",
        {
            "boards": make_paginator(request, board_list),
            "contributors": cache.get_or_set(
                "contributor_count",
                generate_contributor_count(),
                metric_timeout_seconds,
            ),
            "evaluators": cache.get_or_set(
                "evaluator_count", generate_evaluator_count(), metric_timeout_seconds
            ),
            "meta_description": desc,
        },
    )


@require_safe
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
@account_required
def user_board_listing(request, account_id):
    """Return a paginated board listing view for account with account_id."""
    metric_timeout_seconds = 60 * 2

    queries = {
        # default to boards contributed to
        None: lambda x: (
            "contributed to",
            user_boards_contributed(x, viewing_user=request.user),
        ),
        "created": lambda x: (
            "created",
            user_boards_created(x, viewing_user=request.user),
        ),
        "evaluated": lambda x: (
            "evaluated",
            user_boards_evaluated(x, viewing_user=request.user),
        ),
        "contribute": lambda x: (
            "contributed to",
            user_boards_contributed(x, viewing_user=request.user),
        ),
    }

    user = get_object_or_404(User, pk=account_id)
    query = request.GET.get("query")
    verb, board_list = queries.get(query, queries[None])(user)
    desc = _("List of intelligence boards user {username} has {verb}").format(
        username=user.username, verb=verb
    )
    return render(
        request,
        "boards/user_boards.html",
        {
            "user": user,
            "boards": make_paginator(request, board_list),
            "contributors": cache.get_or_set(
                "contributor_count",
                generate_contributor_count(),
                metric_timeout_seconds,
            ),
            "evaluators": cache.get_or_set(
                "evaluator_count", generate_evaluator_count(), metric_timeout_seconds
            ),
            "meta_description": desc,
            "verb": verb,
        },
    )


@require_safe
@account_required
@cache_if_anon(PAGE_CACHE_TIMEOUT_SECONDS)
def detail(request, board_id, dummy_board_slug=None):
    """Return a detail view for the given board.

    Evidence is sorted in order of diagnosticity. Hypotheses are sorted in order of consistency.
    """
    # NOTE: Django's page cache considers full URL including dummy_board_slug. In the future, we may want to adjust
    # the page key to only consider the id and the query parameters.
    # https://docs.djangoproject.com/en/1.10/topics/cache/#the-per-view-cache
    # NOTE: cannot cache page for logged in users b/c comments section contains CSRF and other protection mechanisms.
    view_type = (
        "aggregate"
        if request.GET.get("view_type") is None
        else request.GET["view_type"]
    )

    board = get_object_or_404(Board, pk=board_id)
    permissions = board.permissions.for_user(request.user)

    if "read_board" not in permissions:
        raise PermissionDenied()

    if view_type == "comparison" and not request.user.is_authenticated:
        raise PermissionDenied()

    collaborator_ids = board.collaborator_ids()
    vote_type = request.GET.get(
        "vote_type",
        default=("collab" if request.user.id in collaborator_ids else "all"),
    )

    # calculate aggregate and disagreement for each evidence/hypothesis pair
    all_votes = list(board.evaluation_set.all())
    agg_votes = (
        [x for x in all_votes if x.user_id in collaborator_ids]
        if vote_type == "collab"
        else all_votes
    )

    def _pair_key(evaluation):
        return evaluation.evidence_id, evaluation.hypothesis_id

    keyed = defaultdict(list)
    for vote in agg_votes:
        keyed[_pair_key(vote)].append(Eval(vote.value))
    aggregate = {k: aggregate_vote(v) for k, v in keyed.items()}
    disagreement = {k: calc_disagreement(v) for k, v in keyed.items()}

    user_votes = (
        {_pair_key(v): Eval(v.value) for v in all_votes if v.user_id == request.user.id}
        if request.user.is_authenticated
        else None
    )

    # augment hypotheses and evidence with diagnosticity and consistency
    def _group(first, second, func, key):
        return [(f, func([keyed[key(f, s)] for s in second])) for f in first]

    hypotheses = list(board.hypothesis_set.filter(removed=False))
    evidence = list(board.evidence_set.filter(removed=False))
    hypothesis_consistency = _group(
        hypotheses, evidence, hypothesis_sort_key, key=lambda h, e: (e.id, h.id)
    )
    evidence_diagnosticity = _group(
        evidence, hypotheses, evidence_sort_key, key=lambda e, h: (e.id, h.id)
    )

    return render(
        request,
        "boards/detail.html",
        {
            "board": board,
            "permissions": permissions,
            "evidences": sorted(evidence_diagnosticity, key=lambda e: e[1]),
            "hypotheses": sorted(hypothesis_consistency, key=lambda h: h[1]),
            "view_type": view_type,
            "vote_type": vote_type,
            "votes": aggregate,
            "user_votes": user_votes,
            "disagreement": disagreement,
            "meta_description": board.board_desc,
            "allow_share": not getattr(settings, "ACCOUNT_REQUIRED", False),
            "debug_stats": DEBUG,
        },
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def evaluate(request, board_id, evidence_id):
    """Return a view for assessing a piece of evidence against all hypotheses.

    Take a couple measures to reduce bias: (1) do not show the analyst their previous assessment, and (2) show
    the hypotheses in a random order.
    """
    # Would be nice if we could refactor this and the view to use formsets. Not obvious how to handle the shuffling
    # of the indices that way

    board = get_object_or_404(Board, pk=board_id)

    if "read_board" not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    evidence = get_object_or_404(Evidence, pk=evidence_id)

    default_eval = "------"
    keep_eval = "-- " + _("Keep Previous Assessment")
    remove_eval = "-- " + _("Remove Assessment")

    evaluations = {
        e.hypothesis_id: e
        for e in Evaluation.objects.filter(
            board=board_id, evidence=evidence_id, user=request.user
        )
    }

    hypotheses = [
        (h, evaluations.get(h.id, None))
        for h in Hypothesis.objects.filter(board=board_id)
    ]

    evaluation_set = {str(m.value) for m in Eval}

    if request.method == "POST":
        with transaction.atomic():
            for hypothesis, dummy_evaluation in hypotheses:
                selected = request.POST.get(f"hypothesis-{hypothesis.id}", None)

                evaluation_kwargs = dict(
                    board=board,
                    evidence=evidence,
                    user=request.user,
                    hypothesis=hypothesis,
                )

                if selected == remove_eval:
                    Evaluation.objects.filter(**evaluation_kwargs).delete()
                elif selected in evaluation_set:
                    Evaluation.objects.update_or_create(
                        **evaluation_kwargs,
                        defaults={"value": selected},
                    )
                else:
                    # don't add/update the evaluation
                    pass

            BoardFollower.objects.update_or_create(
                board=board,
                user=request.user,
                defaults={
                    "is_evaluator": True,
                },
            )

        messages.success(
            request,
            _("Recorded evaluations for evidence: {desc}").format(
                desc=evidence.evidence_desc
            ),
        )
        return HttpResponseRedirect(reverse("openach:detail", args=(board_id,)))
    else:
        new_hypotheses = [h for h in hypotheses if h[1] is None]
        old_hypotheses = [h for h in hypotheses if h[1] is not None]
        random.shuffle(old_hypotheses)
        random.shuffle(new_hypotheses)
        return render(
            request,
            "boards/evaluate.html",
            {
                "board": board,
                "evidence": evidence,
                "hypotheses": new_hypotheses + old_hypotheses,
                "options": Evaluation.EVALUATION_OPTIONS,
                "default_eval": default_eval,
                "keep_eval": keep_eval,
                "remove_eval": remove_eval,
            },
        )


@require_safe
@account_required
@cache_on_auth(PAGE_CACHE_TIMEOUT_SECONDS)
def board_history(request, board_id):
    """Return a view with the modification history (board details, evidence, hypotheses) for the board."""

    # this approach to grabbing the history will likely be too slow for big boards
    def _get_history(models):
        changes = [
            FieldHistory.objects.get_for_model(x).select_related("user") for x in models
        ]
        return itertools.chain(*changes)

    board = get_object_or_404(Board, pk=board_id)

    if "read_board" not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    history = [
        _get_history([board]),
        _get_history(Evidence.all_objects.filter(board=board)),
        _get_history(Hypothesis.all_objects.filter(board=board)),
    ]
    history = list(itertools.chain(*history))
    history.sort(key=lambda x: x.date_created, reverse=True)
    return render(
        request, "boards/board_audit.html", {"board": board, "history": history}
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def create_board(request):
    """Return a board creation view, or handle the form submission.

    Set default permissions for the new board. Mark board creator as a board follower.
    """
    if request.method == "POST":
        form = BoardCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                board = form.save(commit=False)
                board.creator = request.user
                board.pub_date = timezone.now()
                board.save()
                for hypothesis_key in ["hypothesis1", "hypothesis2"]:
                    Hypothesis.objects.create(
                        board=board,
                        hypothesis_text=form.cleaned_data[hypothesis_key],
                        creator=request.user,
                    )
                BoardFollower.objects.update_or_create(
                    board=board,
                    user=request.user,
                    defaults={
                        "is_creator": True,
                    },
                )

            return HttpResponseRedirect(reverse("openach:detail", args=(board.id,)))
    else:
        form = BoardCreateForm()
    return render(request, "boards/create_board.html", {"form": form})


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_board(request, board_id):
    """Return a board edit view, or handle the form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if "edit_board" not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    allow_remove = request.user.is_staff and getattr(
        settings, "EDIT_REMOVE_ENABLED", True
    )

    if request.method == "POST":
        form = BoardForm(request.POST, instance=board)
        if "remove" in form.data:
            if allow_remove:
                board.removed = True
                board.save()
                messages.success(
                    request, _("Removed board {name}").format(name=board.board_title)
                )
                return HttpResponseRedirect(reverse("openach:index"))
            else:
                raise PermissionDenied()

        elif form.is_valid():
            form.save()
            messages.success(request, _("Updated board title and/or description."))
            return HttpResponseRedirect(reverse("openach:detail", args=(board.id,)))
    else:
        form = BoardForm(instance=board)

    return render(
        request,
        "boards/edit_board.html",
        {"form": form, "board": board, "allow_remove": allow_remove},
    )


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def edit_permissions(request, board_id):
    """View board permissions form and handle form submission."""
    board = get_object_or_404(Board, pk=board_id)

    if "edit_board" not in board.permissions.for_user(request.user):
        raise PermissionDenied()

    if request.method == "POST":
        form = BoardPermissionForm(
            request.POST, instance=board.permissions, user=request.user
        )
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("openach:detail", args=(board.id,)))
    else:
        form = BoardPermissionForm(instance=board.permissions, user=request.user)

    return render(
        request,
        "boards/edit_permissions.html",
        {
            "board": board,
            "form": form,
        },
    )


@require_safe
@account_required
def board_search(request):
    """Return filtered boards list data in json format."""
    query = request.GET.get("query", "")
    search = Q(board_title__contains=query) | Q(board_desc__contains=query)
    queryset = Board.objects.user_readable(request.user).filter(search)[
        :BOARD_SEARCH_RESULTS_MAX
    ]
    boards = json.dumps(
        [
            {
                "board_title": board.board_title,
                "board_desc": board.board_desc,
                "url": reverse("openach:detail", args=(board.id,)),
            }
            for board in queryset
        ]
    )
    return HttpResponse(boards, content_type="application/json")
