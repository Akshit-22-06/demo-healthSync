from django.conf import settings
from django.db import models


class SymptomCheckSnapshot(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = "LOW", "Low"
        MODERATE = "MODERATE", "Moderate"
        SERIOUS = "SERIOUS", "Serious"
        EMERGENCY = "EMERGENCY", "Emergency"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="symptom_snapshots")
    symptom = models.CharField(max_length=200, blank=True)
    top_condition = models.CharField(max_length=200, blank=True)
    urgency = models.CharField(max_length=40, blank=True)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default=RiskLevel.MODERATE)
    confidence_score = models.FloatField(default=0.0)
    tag_category = models.CharField(max_length=32, blank=True)
    recurrence_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "risk_level"]),
            models.Index(fields=["user", "tag_category"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.risk_level} ({self.tag_category or 'GENERAL'})"


class CommunityAccessTag(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Validation"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_tags")
    tag_code = models.CharField(max_length=64)
    category = models.CharField(max_length=32)
    risk_level = models.CharField(max_length=20, choices=SymptomCheckSnapshot.RiskLevel.choices)
    confidence_score = models.FloatField(default=0.0)
    recurrence_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_community_tags",
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["tag_code"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.tag_code} ({self.status})"


class CommunityRoom(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    category = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"


class CommunityMessage(models.Model):
    room = models.ForeignKey(CommunityRoom, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_messages")
    body = models.TextField(max_length=1500)
    is_blocked = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    moderation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.room.code}: {self.body[:30]}"


class CommunityMessageReport(models.Model):
    message = models.ForeignKey(CommunityMessage, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_message_reports",
    )
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["message", "reported_by"], name="unique_report_per_user_per_message"),
        ]

    def __str__(self) -> str:
        return f"Report by {self.reported_by} on message {self.message_id}"
