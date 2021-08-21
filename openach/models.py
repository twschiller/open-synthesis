"""Analysis of Competing Hypotheses Django Application Model Configuration.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/topics/db/models/
"""
import datetime
import logging
from enum import Enum, unique

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import NoReverseMatch, reverse  # pylint: disable=no-name-in-module
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from field_history.tracker import FieldHistoryTracker
from slugify import slugify

# See database portability constraints here: https://docs.djangoproject.com/en/1.10/ref/databases/#character-fields
URL_MAX_LENGTH = 255
EVIDENCE_MAX_LENGTH = 200
HYPOTHESIS_MAX_LENGTH = 200
BOARD_TITLE_MAX_LENGTH = 200
BOARD_DESC_MAX_LENGTH = 255
SOURCE_TITLE_MAX_LENGTH = 255
SOURCE_DESCRIPTION_MAX_LENGTH = 1000

SLUG_MAX_LENGTH = getattr(settings, "SLUG_MAX_LENGTH", 72)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


# https://docs.djangoproject.com/en/1.10/topics/db/managers/
class RemovableModelManager(models.Manager):  # pylint: disable=too-few-public-methods
    """Query manager that excludes removed models."""

    def get_queryset(self):
        """Return the queryset, excluding removed models."""
        return super(RemovableModelManager, self).get_queryset().filter(removed=False)


@unique
class AuthLevels(Enum):
    """Possible choices for permissions.

    See also settings.INVITE_REQUIRED.
    """

    board_creator = (0, 0)
    collaborators = (1, 1)
    registered = (2, 2)
    anyone = (3, 3)

    def __init__(self, key, ordering):
        """Initialize Board Permission.

        :param key: unique identifier, used in database
        :param ordering: relative level of permissiveness (lower is less permissive)
        """
        self.key = key
        self.ordering = ordering


class BoardModelManager(
    RemovableModelManager
):  # pylint: disable=too-few-public-methods
    """Query manager for permissioned boards."""

    def user_readable(self, user):
        """Queryset for boards that the user has read permissions for."""
        base = super(BoardModelManager, self).get_queryset()
        if user.is_staff:
            return base
        elif not user.is_authenticated:
            return base.filter(permissions__read_board=AuthLevels.anyone.key)
        else:
            public = Q(permissions__read_board=AuthLevels.anyone.key)
            registered = Q(permissions__read_board=AuthLevels.registered.key)
            created = Q(permissions__board__creator=user)
            user_collab = Q(permissions__read_board=AuthLevels.collaborators.key) & Q(
                permissions__collaborators=user
            )
            team_collab = Q(permissions__read_board=AuthLevels.collaborators.key) & Q(
                permissions__teams__members=user
            )
            return base.filter(
                public | registered | created | user_collab | team_collab
            ).distinct()

    def public(self):
        """Queryset for boards that the public can see."""
        return (
            super(BoardModelManager, self)
            .get_queryset()
            .filter(permissions__read_board=AuthLevels.anyone.key)
        )


class Board(models.Model):
    """An ACH matrix with hypotheses, evidence, and evaluations."""

    class Meta:  # pylint: disable=too-few-public-methods
        """Board Model meta options.

        For more information, please see:
          https://docs.djangoproject.com/en/1.10/topics/db/models/#meta-options
        """

        ordering = ("-pub_date",)

    validate_special = RegexValidator(
        r"^((?![!@#^*~`|<>{}+=\[\]]).)*$", "No special characters allowed."
    )
    # When user clicks 'Create Board', validator stops any instance of these characters: !@#^*~`|<>{}+=[]

    board_title = models.CharField(
        max_length=BOARD_TITLE_MAX_LENGTH,
        db_index=True,
        help_text=_(
            "The board title. Typically phrased as a question asking about what happened in the past, "
            "what is happening currently, or what will happen in the future"
        ),
        validators=[validate_special],
    )

    board_slug = models.SlugField(
        null=True, allow_unicode=False, max_length=SLUG_MAX_LENGTH, editable=False
    )

    board_desc = models.CharField(
        "board description",
        max_length=BOARD_DESC_MAX_LENGTH,
        db_index=True,
        help_text=_(
            "A description providing context around the topic. Helps to clarify which hypotheses "
            "and evidence are relevant"
        ),
    )

    creator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    pub_date = models.DateTimeField("date published")

    removed = models.BooleanField(default=False)

    field_history = FieldHistoryTracker(["board_title", "board_desc", "removed"])

    objects = BoardModelManager()

    all_objects = models.Manager()

    def __str__(self):
        """Return a human-readable representation of the board."""
        return self.board_title

    def save(self, *args, **kwargs):
        """Update slug on save."""
        self.board_slug = slugify(self.board_title, max_length=SLUG_MAX_LENGTH)
        return super().save(*args, **kwargs)

    def was_published_recently(self):
        """Return True iff the Board was created recently."""
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now

    def get_absolute_url(self):
        """Return the absolute URL for viewing the board details, including the slug."""
        if self.board_slug:
            try:
                return reverse(
                    "openach:detail_slug",
                    args=(
                        self.id,
                        self.board_slug,
                    ),
                )
            except NoReverseMatch:
                logger.warning(
                    "Malformed SLUG for reverse URL match: %s", self.board_slug
                )
                return reverse("openach:detail", args=(self.id,))
        else:
            return self.get_canonical_url()

    def get_canonical_url(self):
        """Return the canonical URL for view board details, excluding the slug."""
        return reverse("openach:detail", args=(self.id,))

    def is_collaborator(self, user):
        """Return True if the user is a collaborator on the board.

        Checks for direct collaboration and collaboration via a team.
        """
        return (
            self.permissions.collaborators.filter(pk=user.id).exists()
            or self.permissions.teams.filter(members__pk=user.id).exists()
        )

    def collaborator_ids(self):
        """Return set of collaborator ids for the board."""
        direct = set(self.permissions.collaborators.values_list("id", flat=True))
        team = set(
            Team.objects.filter(pk__in=self.permissions.teams.all())
            .values_list("members__id", flat=True)
            .distinct()
        )
        return direct | team

    def can_read(self, user):
        """Return True if user can read the board."""
        return "read_board" in self.permissions.for_user(user)

    def has_collaborators(self):
        """Return True if the board has collaborators set."""
        return (
            self.permissions.collaborators.exists() or self.permissions.teams.exists()
        )

    def has_follower(self, user):
        """Return true iff user follows this board."""
        return self.followers.filter(user=user).exists()


# https://docs.djangoproject.com/en/1.10/topics/db/managers/
class TeamModelManager(models.Manager):  # pylint: disable=too-few-public-methods
    def user_visible(self, user):
        """Return teams visible to the given user.

        Includes public teams and teams the user is a member of or invited to.
        """
        if user is None or not user.is_authenticated:
            return super().get_queryset().filter(public=True)
        else:
            user_teams = user.team_set.values_list("id", flat=True)
            invited = TeamRequest.objects.filter(
                inviter__isnull=False, invitee=user
            ).values_list("team", flat=True)
            return (
                super()
                .get_queryset()
                .filter(Q(public=True) | Q(id__in=user_teams) | Q(id__in=invited))
                .distinct()
            )


class Team(models.Model):
    """Analysis team."""

    objects = TeamModelManager()

    creator = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    owner = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    name = models.CharField(max_length=64, unique=True)

    description = models.TextField(blank=True)

    url = models.URLField(null=True, blank=True)

    members = models.ManyToManyField(User, blank=True, editable=False)

    public = models.BooleanField(
        default=True, help_text=_("Whether or not the team is visible to non-members")
    )

    invitation_required = models.BooleanField(default=True)

    create_timestamp = models.DateTimeField(auto_now_add=True)

    field_history = FieldHistoryTracker(
        ["name", "description", "url", "public", "invitation_required"]
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("openach:view_team", args=(self.id,))


class TeamRequest(models.Model):
    """Request to join a team or invitation to a team.

    - If inviter and invitee is set, the request is an invitation to join the team.
    - If the invitee is set, the request is a request to join a team.
    """

    class Meta:
        unique_together = (("team", "inviter", "invitee"),)

    team = models.ForeignKey(Team, on_delete=models.CASCADE)

    inviter = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.CASCADE,
    )

    invitee = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="team_invites",
        on_delete=models.CASCADE,
    )

    create_timestamp = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.inviter is None and self.invitee is None:
            raise ValidationError(_("Team membership request must have an initiator"))


class BoardPermissions(models.Model):
    """Permissions for the board."""

    AUTH_CHOICES = [
        (AuthLevels.board_creator.key, _("Only Me")),
        (AuthLevels.collaborators.key, _("Collaborators")),
        (AuthLevels.registered.key, _("Registered Users")),
        (AuthLevels.anyone.key, _("Public")),
    ]

    AUTH_CHOICES_REGISTERED = [
        (AuthLevels.board_creator.key, _("Only Me")),
        (AuthLevels.collaborators.key, _("Collaborators")),
        (AuthLevels.registered.key, _("Registered Users")),
    ]

    PERMISSION_NAMES = [
        "read_board",
        "read_comments",
        "add_comments",
        "add_elements",
        "edit_elements",
        "edit_board",
    ]

    PERMISSION_NAMES_READ = [
        "read_board",
        "read_comments",
    ]

    board = models.OneToOneField(
        Board,
        related_name="permissions",
        on_delete=models.CASCADE,
    )

    collaborators = models.ManyToManyField(
        User,
        blank=True,
    )

    teams = models.ManyToManyField(
        Team,
        blank=True,
    )

    read_board = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES,
        help_text=_("Who can view the board?"),
        default=AuthLevels.anyone.key,
    )

    read_comments = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES,
        help_text=_("Who can view board comments?"),
        default=AuthLevels.anyone.key,
    )

    add_comments = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES_REGISTERED,
        help_text=_("Who can comment on the board?"),
        default=AuthLevels.collaborators.key,
    )

    add_elements = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES_REGISTERED,
        help_text=_("Who can add hypotheses, evidence, and sources?"),
        default=AuthLevels.collaborators.key,
    )

    edit_elements = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES_REGISTERED,
        help_text=_("Who can edit hypotheses, evidence, and sources?"),
        default=AuthLevels.collaborators.key,
    )

    edit_board = models.PositiveSmallIntegerField(
        choices=AUTH_CHOICES_REGISTERED,
        help_text=_("Who can edit the board title, description, and permissions?"),
        default=AuthLevels.board_creator.key,
    )

    def make_public(self):
        """Set permissions to the most permissive permission scheme."""
        account_required = getattr(settings, "ACCOUNT_REQUIRED", False)

        for permission in self.PERMISSION_NAMES:
            public_perm = (
                AuthLevels.anyone.key
                if permission in self.PERMISSION_NAMES_READ and not account_required
                else AuthLevels.registered.key
            )
            setattr(self, permission, public_perm)
        self.save()

    def update_all(self, auth_level):
        """Set all permissions to  auth_level"""
        for permission in self.PERMISSION_NAMES:
            setattr(self, permission, auth_level.key)
        self.save()

    def for_user(self, user):
        """Return board authorization scheme for the given user.

        If user is not authenticated, only the read_board and read_comments can be made available. NOTE: global public
        access should be controlled via the ACCOUNT_REQUIRED settings.
        """
        max_allowed = (
            BoardPermissions.PERMISSION_NAMES
            if user.is_authenticated
            else BoardPermissions.PERMISSION_NAMES_READ
        )

        is_owner = (
            self.board.creator_id is not None and user.id == self.board.creator_id
        )

        if user.is_staff or is_owner:
            return set(max_allowed)
        else:
            is_user_collaborator = self.collaborators.filter(pk=user.id).exists()
            is_team_collaborator = self.teams.filter(members__pk=user.id).exists()
            is_collaborator = is_user_collaborator or is_team_collaborator

            def check_allowed(permission):
                level = getattr(self, permission, AuthLevels.board_creator.key)
                return (
                    level == AuthLevels.anyone.key
                    or (level == AuthLevels.registered.key and user.is_authenticated)
                    or (level == AuthLevels.collaborators.key and is_collaborator)
                )

            return set(filter(check_allowed, max_allowed))

    def clean(self):
        """Validate the BoardPermissions model.

        Check that the read permission is valid with respect to the relative to the global ACCOUNT_REQUIRED setting.
        Check that the other permissions are valid relative to
        """
        super(BoardPermissions, self).clean()

        errors = {}

        if (
            getattr(settings, "ACCOUNT_REQUIRED", True)
            and self.read_board == AuthLevels.collaborators.anyone.key
        ):
            errors["read_board"] = _(
                "Cannot set permission to public because site permits only registered users"
            )
        if self.add_comments > self.read_comments:
            errors["add_comments"] = _(
                'Cannot be more permissive than the "read comments" permission'
            )
        if self.edit_elements > self.add_elements:
            errors["edit_elements"] = _(
                'Cannot be more permissive than the "add elements" permission'
            )
        if self.read_comments > self.read_board:
            errors["read_comments"] = _(
                'Cannot be more permissive than the "read board" permission'
            )
        if self.add_elements > self.read_board:
            errors["add_elements"] = _(
                'Cannot be more permissive than the "read board" permission'
            )
        if self.edit_board > self.edit_elements:
            errors["edit_board"] = _(
                'Cannot be more permissive than the "edit elements" permission'
            )

        if len(errors) > 0:
            raise ValidationError(errors)


class BoardFollower(models.Model):
    """Follower relationship between a user and a board."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="followers")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_creator = models.BooleanField(default=False)
    is_contributor = models.BooleanField(default=False)
    is_evaluator = models.BooleanField(default=False)
    update_timestamp = models.DateTimeField(auto_now=True)


class Hypothesis(models.Model):
    """An ACH matrix hypothesis."""

    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
    )

    hypothesis_text = models.CharField(
        "hypothesis",
        max_length=HYPOTHESIS_MAX_LENGTH,
    )

    creator = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
    )

    submit_date = models.DateTimeField(
        "date added",
        auto_now_add=True,
    )

    removed = models.BooleanField(
        default=False,
    )

    field_history = FieldHistoryTracker(["hypothesis_text", "removed"])

    objects = RemovableModelManager()

    all_objects = models.Manager()

    class Meta:  # pylint: disable=too-few-public-methods
        """Hypothesis Model meta options.

        For more information, please see:
            https://docs.djangoproject.com/en/1.10/topics/db/models/#meta-options
        """

        verbose_name_plural = _("hypotheses")

    def __str__(self):
        """Return a human-readable representation of the hypothesis."""
        return self.hypothesis_text


class Evidence(models.Model):
    """A piece of evidence for an ACH matrix."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE)

    creator = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
    )

    evidence_desc = models.CharField(
        "evidence description",
        max_length=EVIDENCE_MAX_LENGTH,
        help_text=_(
            "A short summary of the evidence. Use the event date field for capturing the date"
        ),
    )

    event_date = models.DateField(
        "evidence event date",
        # Don't require evidence date because some evidence doesn't have a fixed start date. However, it can be useful
        # to sort evidence by when it occurred, therefore in the future we might want to allow setting a year, month,
        # or complete date
        null=True,
        blank=True,
        help_text=_("The date the event occurred or started"),
    )

    submit_date = models.DateTimeField("date added", auto_now_add=True)

    removed = models.BooleanField(default=False)

    field_history = FieldHistoryTracker(["evidence_desc", "event_date", "removed"])

    objects = RemovableModelManager()
    all_objects = models.Manager()

    class Meta:  # pylint: disable=too-few-public-methods
        """Evidence Model meta options.

        For more information, please see:
            https://docs.djangoproject.com/en/1.10/topics/db/models/#meta-options
        """

        verbose_name_plural = _("evidence")

    def __str__(self):
        """Return a human-readable representation of the evidence."""
        return self.evidence_desc

    def get_canonical_url(self):
        """Return the canonical URL for view evidence details."""
        return reverse("openach:evidence_detail", args=(self.id,))


class EvidenceSource(models.Model):
    """A source for a piece of evidence in the ACH matrix."""

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
    )

    source_url = models.URLField(
        "source website",
        max_length=URL_MAX_LENGTH,
        help_text=_(
            "A source (e.g., news article or press release) corroborating the evidence"
        ),
    )

    source_title = models.CharField(
        "source title",
        max_length=SOURCE_TITLE_MAX_LENGTH,
        default="",
    )

    source_description = models.CharField(
        "source description",
        max_length=SOURCE_DESCRIPTION_MAX_LENGTH,
        default="",
    )

    source_date = models.DateField(
        "source date",
        help_text=_(
            "The date the source released or last updated the information corroborating the evidence. "
            "Typically the date of the article or post"
        ),
    )

    uploader = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
    )

    submit_date = models.DateTimeField(
        "date added",
        auto_now_add=True,
    )

    corroborating = models.BooleanField()

    removed = models.BooleanField(default=False)

    objects = RemovableModelManager()
    all_objects = models.Manager()


class EvidenceSourceTag(models.Model):
    """A tag that an analyst can apply to an evidence source."""

    tag_name = models.CharField(max_length=64, unique=True)
    tag_desc = models.CharField(max_length=200)

    def __str__(self):
        """Return a human-readable representation of the source tag."""
        return "{}: {}".format(self.tag_name, self.tag_desc)


class AnalystSourceTag(models.Model):
    """An instance of an analyst tagging an evidence source with a tag."""

    source = models.ForeignKey(EvidenceSource, on_delete=models.CASCADE)
    tagger = models.ForeignKey(User, on_delete=models.CASCADE)
    tag = models.ForeignKey(EvidenceSourceTag, on_delete=models.CASCADE)
    tag_date = models.DateTimeField("date tagged", auto_now_add=True)


@unique
class Eval(Enum):
    """Possible choices for evaluating a hypothesis with respect to a piece of evidence."""

    not_applicable = 0
    very_inconsistent = 1
    inconsistent = 2
    neutral = 3
    consistent = 4
    very_consistent = 5


class Evaluation(models.Model):
    """A user's evaluation of a hypothesis with respect to a piece of evidence."""

    EVALUATION_OPTIONS = (
        (Eval.not_applicable.value, _("N/A")),
        (Eval.very_inconsistent.value, _("Very Inconsistent")),
        (Eval.inconsistent.value, _("Inconsistent")),
        (Eval.neutral.value, _("Neutral")),
        (Eval.consistent.value, _("Consistent")),
        (Eval.very_consistent.value, _("Very Consistent")),
    )
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    hypothesis = models.ForeignKey(Hypothesis, on_delete=models.CASCADE)
    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField("date evaluated", auto_now=True)
    value = models.PositiveSmallIntegerField(default=0, choices=EVALUATION_OPTIONS)

    def __str__(self):
        """Return a human-readable representation of the evaluation."""
        # NOTE: Django's ORM automatically generates a get_xxx_display() member variable
        return self.get_value_display()  # pylint: disable=no-member


class ProjectNews(models.Model):
    """A news alert for the front page."""

    class Meta:
        verbose_name_plural = "project news"

    content = models.CharField(max_length=1024)

    pub_date = models.DateTimeField("date published")

    author = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
    )


@unique
class DigestFrequency(Enum):
    """Possible choices for receiving email digests."""

    never = (0, None)
    daily = (1, timezone.timedelta(days=1))
    weekly = (2, timezone.timedelta(days=7))

    def __init__(self, key, delta):
        """Initialize Digest Frequency.

        :param key: unique identifier, used in database
        :param delta: timedelta covered by the frequency, or None (e.g., 7 days)
        """
        self.key = key
        self.delta = delta


class UserSettings(models.Model):
    """User account preferences."""

    DIGEST_FREQUENCY = (
        (DigestFrequency.never.key, _("Never")),
        (DigestFrequency.daily.key, _("Daily")),
        (DigestFrequency.weekly.key, _("Weekly")),
    )

    user = models.OneToOneField(
        User,
        related_name="settings",
        on_delete=models.CASCADE,
    )

    digest_frequency = models.PositiveSmallIntegerField(
        _("email digest frequency"),
        default=DigestFrequency.daily.key,
        choices=DIGEST_FREQUENCY,
        help_text=_(
            "How frequently to receive email updates containing new notifications"
        ),
    )


class DigestStatus(models.Model):
    """Email digest status."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )

    last_success = models.DateTimeField(
        null=True,
        default=None,
    )

    last_attempt = models.DateTimeField(
        null=True,
        default=None,
    )
