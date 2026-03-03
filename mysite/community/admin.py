from django.contrib import admin
from django.utils import timezone

from community.models import (
    CommunityAccessTag,
    CommunityMessage,
    CommunityMessageReport,
    CommunityRoom,
    SymptomCheckSnapshot,
)


@admin.action(description="Approve selected community tags")
def approve_tags(modeladmin, request, queryset):
    now = timezone.now()
    for tag in queryset:
        tag.status = CommunityAccessTag.Status.APPROVED
        tag.reviewed_at = now
        tag.reviewed_by = request.user
        if not tag.requested_at:
            tag.requested_at = now
        tag.save(
            update_fields=[
                "status",
                "reviewed_at",
                "reviewed_by",
                "requested_at",
                "updated_at",
            ]
        )


@admin.action(description="Reject selected community tags")
def reject_tags(modeladmin, request, queryset):
    now = timezone.now()
    for tag in queryset:
        tag.status = CommunityAccessTag.Status.REJECTED
        tag.reviewed_at = now
        tag.reviewed_by = request.user
        tag.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])


@admin.register(SymptomCheckSnapshot)
class SymptomCheckSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "risk_level", "tag_category", "confidence_score", "recurrence_count", "created_at")
    list_filter = ("risk_level", "tag_category", "created_at")
    search_fields = ("user__username", "user__email", "symptom", "top_condition")
    readonly_fields = (
        "user",
        "symptom",
        "top_condition",
        "urgency",
        "risk_level",
        "confidence_score",
        "tag_category",
        "recurrence_count",
        "created_at",
    )


@admin.register(CommunityAccessTag)
class CommunityAccessTagAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tag_code",
        "status",
        "category",
        "risk_level",
        "confidence_score",
        "recurrence_count",
        "requested_at",
        "reviewed_at",
    )
    list_filter = ("status", "category", "risk_level", "created_at")
    search_fields = ("user__username", "user__email", "tag_code", "category")
    actions = [approve_tags, reject_tags]


@admin.register(CommunityRoom)
class CommunityRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "code", "description")


@admin.register(CommunityMessage)
class CommunityMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "is_blocked", "is_flagged", "created_at")
    list_filter = ("room", "is_blocked", "is_flagged", "created_at")
    search_fields = ("user__username", "body", "moderation_reason")


@admin.register(CommunityMessageReport)
class CommunityMessageReportAdmin(admin.ModelAdmin):
    list_display = ("message", "reported_by", "reason", "created_at")
    list_filter = ("created_at",)
    search_fields = ("reported_by__username", "reason", "message__body")
