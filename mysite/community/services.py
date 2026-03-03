from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils.text import slugify
from django.utils import timezone

from community.models import CommunityAccessTag, CommunityMessage, CommunityRoom, SymptomCheckSnapshot

SERIOUS_CONFIDENCE_THRESHOLD = 0.60
SERIOUS_RECURRENCE_THRESHOLD = 1
SERIOUS_WINDOW_DAYS = 90
CHAT_CATEGORY = "GROUP"

ROOM_PRESETS: tuple[tuple[str, str, str, str], ...] = (
    (
        "community-support-chat",
        CHAT_CATEGORY,
        "Community Support Chat",
        "Unified group chat for users with validated access.",
    ),
)

SUPPORT_KEYWORDS: tuple[str, ...] = (
    "anxiety",
    "autism",
    "adhd",
    "developmental delay",
    "depression",
    "down syndrome",
    "intellectual disability",
    "learning disability",
    "cognitive disorder",
    "cognitive impairment",
    "panic",
    "stress",
    "insomnia",
    "trauma",
    "ptsd",
    "bipolar",
    "mood",
    "schizo",
    "ocd",
    "self harm",
    "suicidal",
    "hallucination",
)

EMERGENCY_PHRASES: tuple[str, ...] = (
    "cannot breathe",
    "can't breathe",
    "severe chest pain",
    "unconscious",
    "heavy bleeding",
    "suicidal",
    "suicide",
)

HARMFUL_ADVICE_PHRASES: tuple[str, ...] = (
    "stop your medicine",
    "ignore doctor",
    "don't go to hospital",
    "dont go to hospital",
    "overdose",
    "take double dose",
    "self medicate",
)

LIKELIHOOD_TO_CONFIDENCE: dict[str, float] = {
    "very high": 0.92,
    "high": 0.84,
    "moderate": 0.70,
    "medium": 0.70,
    "low": 0.52,
    "very low": 0.40,
}


def ensure_default_rooms() -> None:
    for code, category, name, description in ROOM_PRESETS:
        room, created = CommunityRoom.objects.get_or_create(
            code=code,
            defaults={
                "category": category,
                "name": name,
                "description": description,
                "is_active": True,
            },
        )
        if not created:
            changed = False
            if room.category != category:
                room.category = category
                changed = True
            if room.name != name:
                room.name = name
                changed = True
            if room.description != description:
                room.description = description
                changed = True
            if not room.is_active:
                room.is_active = True
                changed = True
            if changed:
                room.save(update_fields=["category", "name", "description", "is_active"])

    CommunityRoom.objects.exclude(category=CHAT_CATEGORY).update(is_active=False)


def normalize_risk_level(urgency: str) -> str:
    normalized = (urgency or "").strip().lower()
    if normalized in {"emergency", "critical"}:
        return SymptomCheckSnapshot.RiskLevel.EMERGENCY
    if normalized in {"high", "serious"}:
        return SymptomCheckSnapshot.RiskLevel.SERIOUS
    if normalized == "moderate":
        return SymptomCheckSnapshot.RiskLevel.MODERATE
    return SymptomCheckSnapshot.RiskLevel.LOW


def _estimate_confidence(diagnosis: dict) -> float:
    conditions = diagnosis.get("conditions") or []
    if conditions and isinstance(conditions[0], dict):
        likelihood = str(conditions[0].get("likelihood", "")).strip().lower()
        if likelihood in LIKELIHOOD_TO_CONFIDENCE:
            return LIKELIHOOD_TO_CONFIDENCE[likelihood]
    urgency = (diagnosis.get("urgency") or "").strip().lower()
    if urgency in {"high", "serious"}:
        return 0.72
    if urgency == "moderate":
        return 0.62
    return 0.48


def _top_condition_name(diagnosis: dict) -> str:
    conditions = diagnosis.get("conditions") or []
    if not conditions:
        return ""
    first = conditions[0]
    if not isinstance(first, dict):
        return ""
    return (first.get("name") or "").strip()


def _infer_category(*, symptom: str, top_condition: str) -> str:
    source = f"{symptom} {top_condition}".strip().lower()
    if not source:
        return "GENERAL"
    if any(token in source for token in SUPPORT_KEYWORDS):
        return CHAT_CATEGORY
    return "GENERAL"


def _build_tag_code(*, category: str, recurrence_count: int) -> str:
    severity = "CHRONIC" if recurrence_count >= 3 else "SEVERE"
    return f"{category}_{severity}"


def _is_authenticated_user(user) -> bool:
    if not user:
        return False
    if isinstance(user, AnonymousUser):
        return False
    return bool(getattr(user, "is_authenticated", False))


def _serious_count_for_category(*, user, category: str) -> int:
    window_start = timezone.now() - timedelta(days=SERIOUS_WINDOW_DAYS)
    return SymptomCheckSnapshot.objects.filter(
        user=user,
        risk_level=SymptomCheckSnapshot.RiskLevel.SERIOUS,
        tag_category=category,
        created_at__gte=window_start,
    ).count()


def evaluate_community_eligibility(*, user, intake: dict, diagnosis: dict) -> dict:
    outcome = {
        "status": "locked",
        "tag_code": "",
        "category": "",
        "risk_level": SymptomCheckSnapshot.RiskLevel.LOW,
        "confidence_score": 0.0,
        "recurrence_count": 0,
        "requires_admin_review": False,
        "community_url": "/community/",
        "message": "Complete a Symptom Checker session to determine community eligibility.",
    }
    if not _is_authenticated_user(user):
        outcome["message"] = "Login is required to unlock community eligibility from Symptom Checker."
        return outcome

    symptom = str((intake or {}).get("symptom", "")).strip()
    urgency = str((diagnosis or {}).get("urgency", "")).strip()
    top_condition = _top_condition_name(diagnosis)
    confidence = _estimate_confidence(diagnosis)
    risk_level = normalize_risk_level(urgency)
    category = _infer_category(symptom=symptom, top_condition=top_condition)

    historical_serious = _serious_count_for_category(user=user, category=category)
    recurrence_count = historical_serious + (1 if category == CHAT_CATEGORY else 0)

    SymptomCheckSnapshot.objects.create(
        user=user,
        symptom=symptom[:200],
        top_condition=top_condition[:200],
        urgency=urgency[:40],
        risk_level=risk_level,
        confidence_score=confidence,
        tag_category=category,
        recurrence_count=recurrence_count,
    )

    outcome.update(
        {
            "category": category,
            "risk_level": risk_level,
            "confidence_score": round(confidence, 2),
            "recurrence_count": recurrence_count,
        }
    )

    if risk_level == SymptomCheckSnapshot.RiskLevel.EMERGENCY:
        outcome["status"] = "emergency"
        outcome["message"] = "Emergency risk detected. Community chat is disabled; seek immediate medical care."
        return outcome

    if category != CHAT_CATEGORY:
        outcome["message"] = "Assessment does not match current chat access category."
        return outcome

    if confidence < SERIOUS_CONFIDENCE_THRESHOLD:
        outcome["message"] = (
            "Serious risk detected but confidence is below threshold. "
            "Repeat Symptom Checker if symptoms persist."
        )
        return outcome

    if recurrence_count < SERIOUS_RECURRENCE_THRESHOLD:
        outcome["message"] = (
            f"Serious risk found. Recurrence check is {recurrence_count}/{SERIOUS_RECURRENCE_THRESHOLD}; "
            "community tag will generate after recurrence threshold is met."
        )
        return outcome

    tag_code = _build_tag_code(category=category, recurrence_count=recurrence_count)
    room_seed = top_condition or symptom or "Community Support"
    group_room = _ensure_group_room(room_seed)
    tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            category=CHAT_CATEGORY,
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    now = timezone.now()
    if tag is None:
        tag = CommunityAccessTag.objects.create(
            user=user,
            tag_code=tag_code,
            category=CHAT_CATEGORY,
            risk_level=risk_level,
            confidence_score=confidence,
            recurrence_count=recurrence_count,
            status=CommunityAccessTag.Status.APPROVED,
            requested_at=now,
            reviewed_at=now,
        )
    else:
        tag.tag_code = tag_code
        tag.risk_level = risk_level
        tag.confidence_score = confidence
        tag.recurrence_count = recurrence_count
        tag.status = CommunityAccessTag.Status.APPROVED
        if not tag.requested_at:
            tag.requested_at = now
        if not tag.reviewed_at:
            tag.reviewed_at = now
        tag.save(
            update_fields=[
                "tag_code",
                "risk_level",
                "confidence_score",
                "recurrence_count",
                "status",
                "requested_at",
                "reviewed_at",
                "updated_at",
            ]
        )

    outcome.update(
        {
            "status": "approved",
            "tag_code": tag.tag_code,
            "requires_admin_review": False,
            "message": "Access approved. You can join chat.",
            "community_url": f"/community/room/{group_room.code}/",
        }
    )
    return outcome


def _latest_emergency_snapshot(user) -> SymptomCheckSnapshot | None:
    return (
        SymptomCheckSnapshot.objects.filter(
            user=user,
            risk_level=SymptomCheckSnapshot.RiskLevel.EMERGENCY,
        )
        .order_by("-created_at")
        .first()
    )


def _trim_preview(text: str, *, limit: int = 44) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _room_code_for_group(seed: str) -> str:
    slug = slugify((seed or "").strip())[:42] or "support"
    return f"group-{slug}"


def _ensure_group_room(group_seed: str) -> CommunityRoom:
    group_name = (group_seed or "").strip() or "Community Support"
    room_code = _room_code_for_group(group_name)
    room, created = CommunityRoom.objects.get_or_create(
        code=room_code,
        defaults={
            "category": CHAT_CATEGORY,
            "name": f"{group_name} Group",
            "description": f"Support chat for {group_name}.",
            "is_active": True,
        },
    )
    if not created:
        changed = False
        expected_name = f"{group_name} Group"
        expected_desc = f"Support chat for {group_name}."
        if room.name != expected_name:
            room.name = expected_name
            changed = True
        if room.description != expected_desc:
            room.description = expected_desc
            changed = True
        if not room.is_active:
            room.is_active = True
            changed = True
        if changed:
            room.save(update_fields=["name", "description", "is_active"])
    return room


def user_community_context(user) -> dict:
    ensure_default_rooms()

    approved_tags = list(
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.APPROVED,
            category=CHAT_CATEGORY,
        ).order_by("-reviewed_at")
    )
    pending_tags = list(
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.PENDING,
            category=CHAT_CATEGORY,
        ).order_by("-created_at")
    )
    latest_snapshot = SymptomCheckSnapshot.objects.filter(user=user).order_by("-created_at").first()
    emergency_snapshot = _latest_emergency_snapshot(user)

    rooms = list(CommunityRoom.objects.filter(is_active=True, category=CHAT_CATEGORY).order_by("name"))
    if latest_snapshot and (latest_snapshot.top_condition or latest_snapshot.symptom):
        room_seed = latest_snapshot.top_condition or latest_snapshot.symptom
        preferred_code = _room_code_for_group(room_seed)
        preferred_room = CommunityRoom.objects.filter(code=preferred_code, is_active=True).first()
        if preferred_room:
            rooms = [preferred_room]
    if not approved_tags:
        rooms = []

    room_previews: list[dict] = []
    for room in rooms:
        room_messages = CommunityMessage.objects.filter(room=room, is_blocked=False).select_related("user").order_by(
            "-created_at"
        )
        latest_message = room_messages.first()
        room_previews.append(
            {
                "room": room,
                "group_name": room.name,
                "total_messages": room_messages.count(),
                "latest_sender": latest_message.user.username if latest_message else "",
                "latest_preview": _trim_preview(latest_message.body if latest_message else "No messages yet."),
                "latest_time": latest_message.created_at if latest_message else None,
            }
        )

    can_access = bool(approved_tags) and emergency_snapshot is None
    if emergency_snapshot:
        locked_reason = (
            "Emergency severity was detected in your latest serious assessment. "
            "Community access is blocked for safety."
        )
    elif pending_tags:
        locked_reason = "Your serious-condition tag is pending admin validation."
    elif latest_snapshot is None:
        locked_reason = "Complete a Symptom Checker session to determine eligibility."
    elif latest_snapshot.tag_category != CHAT_CATEGORY:
        locked_reason = "Latest assessment does not match current chat access category."
    else:
        locked_reason = "No approved access tag yet. Community remains locked."

    return {
        "can_access": can_access,
        "rooms": rooms,
        "room_previews": room_previews,
        "approved_tags": approved_tags,
        "pending_tags": pending_tags,
        "latest_snapshot": latest_snapshot,
        "locked_reason": locked_reason,
    }


def request_pending_access(user) -> tuple[bool, str]:
    approved = CommunityAccessTag.objects.filter(
        user=user,
        status=CommunityAccessTag.Status.APPROVED,
        category=CHAT_CATEGORY,
    ).exists()
    if approved:
        return True, "Community access is already approved."

    pending_tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.PENDING,
            category=CHAT_CATEGORY,
        )
        .order_by("-created_at")
        .first()
    )
    if not pending_tag:
        return False, "No pending serious-condition tag found. Complete Symptom Checker first."

    pending_tag.requested_at = timezone.now()
    pending_tag.save(update_fields=["requested_at", "updated_at"])
    return True, "Community access request submitted for admin validation."


def can_user_access_room(*, user, room: CommunityRoom) -> tuple[bool, str, CommunityAccessTag | None]:
    if _latest_emergency_snapshot(user):
        return False, "Community access is blocked due to emergency severity status.", None
    if room.category != CHAT_CATEGORY:
        return False, "Only the community support room is enabled.", None

    approved_tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.APPROVED,
            category=CHAT_CATEGORY,
        )
        .order_by("-reviewed_at", "-created_at")
        .first()
    )
    if not approved_tag:
        return False, "You are not validated for this community category.", None
    return True, "", approved_tag


def moderate_chat_message(text: str) -> tuple[bool, str]:
    normalized = (text or "").strip().lower()
    if len(normalized) < 2:
        return False, "Message is too short."

    for phrase in EMERGENCY_PHRASES:
        if phrase in normalized:
            return False, "Emergency phrase detected. Please seek emergency care instead of chat."
    for phrase in HARMFUL_ADVICE_PHRASES:
        if phrase in normalized:
            return False, "Unsafe advice detected. Message was blocked for safety."
    return True, ""
