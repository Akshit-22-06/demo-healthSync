from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from community.catalog import *  # noqa: F401,F403
from community.models import CommunityAccessTag, CommunityMessage, CommunityRoom, SymptomCheckSnapshot

MIN_CONFIDENCE_FOR_AUTO_APPROVAL = 0.60
MIN_SERIOUS_CASES_FOR_AUTO_APPROVAL = 1
SERIOUS_CASE_LOOKBACK_DAYS = 90


def sync_default_community_rooms() -> None:
    for code, category, name, description in DEFAULT_COMMUNITY_ROOMS:
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

    preset_codes = [code for code, _, _, _ in DEFAULT_COMMUNITY_ROOMS]
    CommunityRoom.objects.exclude(code__in=preset_codes).update(is_active=False)


def map_urgency_to_risk_level(urgency: str) -> str:
    normalized = (urgency or "").strip().lower()
    if normalized in {"emergency", "critical"}:
        return SymptomCheckSnapshot.RiskLevel.EMERGENCY
    if normalized in {"high", "serious"}:
        return SymptomCheckSnapshot.RiskLevel.SERIOUS
    if normalized == "moderate":
        return SymptomCheckSnapshot.RiskLevel.MODERATE
    return SymptomCheckSnapshot.RiskLevel.LOW


def estimate_confidence_from_diagnosis(diagnosis: dict) -> float:
    conditions = diagnosis.get("conditions") or []
    if conditions and isinstance(conditions[0], dict):
        likelihood = str(conditions[0].get("likelihood", "")).strip().lower()
        if likelihood in LIKELIHOOD_CONFIDENCE_MAP:
            return LIKELIHOOD_CONFIDENCE_MAP[likelihood]
    urgency = (diagnosis.get("urgency") or "").strip().lower()
    if urgency in {"high", "serious"}:
        return 0.72
    if urgency == "moderate":
        return 0.62
    return 0.48


def extract_top_condition_name(diagnosis: dict) -> str:
    conditions = diagnosis.get("conditions") or []
    if not conditions:
        return ""
    first = conditions[0]
    if not isinstance(first, dict):
        return ""
    return (first.get("name") or "").strip()


def parse_intake_age(intake: dict) -> int | None:
    raw = (intake or {}).get("age")
    if raw in (None, ""):
        return None
    try:
        age = int(raw)
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


def contains_any_keyword(source: str, keywords: tuple[str, ...]) -> bool:
    return any(token in source for token in keywords)


def infer_condition_category(*, symptom: str, top_condition: str, age: int | None) -> str:
    source = f"{symptom} {top_condition}".strip().lower()
    if age is not None and age >= 60:
        return CATEGORY_SENIOR
    if age is not None and age <= 16 and contains_any_keyword(
        source, CATEGORY_KEYWORDS[CATEGORY_CHILD_DEV]
    ):
        return CATEGORY_CHILD_DEV

    for category in CATEGORY_MATCH_PRIORITY:
        if contains_any_keyword(source, CATEGORY_KEYWORDS.get(category, ())):
            return category
    return CATEGORY_GENERAL


def build_community_tag_code(*, category: str, recurrence_count: int) -> str:
    severity = "CHRONIC" if recurrence_count >= 3 else "SEVERE"
    return f"{category}_{severity}"


def is_authenticated_app_user(user) -> bool:
    if not user:
        return False
    if isinstance(user, AnonymousUser):
        return False
    return bool(getattr(user, "is_authenticated", False))


def count_recent_serious_cases_for_category(*, user, category: str) -> int:
    window_start = timezone.now() - timedelta(days=SERIOUS_CASE_LOOKBACK_DAYS)
    return SymptomCheckSnapshot.objects.filter(
        user=user,
        risk_level=SymptomCheckSnapshot.RiskLevel.SERIOUS,
        tag_category=category,
        created_at__gte=window_start,
    ).count()


def get_active_room_for_category(category: str) -> CommunityRoom | None:
    room_code = CATEGORY_TO_ROOM_CODE.get(category)
    if not room_code:
        return None
    return CommunityRoom.objects.filter(code=room_code, is_active=True).first()


def evaluate_chat_access_eligibility(*, user, intake: dict, diagnosis: dict) -> dict:
    access_decision = {
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
    if not is_authenticated_app_user(user):
        access_decision["message"] = "Login is required to unlock community eligibility from Symptom Checker."
        return access_decision

    sync_default_community_rooms()

    symptom = str((intake or {}).get("symptom", "")).strip()
    urgency = str((diagnosis or {}).get("urgency", "")).strip()
    top_condition = extract_top_condition_name(diagnosis)
    confidence = estimate_confidence_from_diagnosis(diagnosis)
    risk_level = map_urgency_to_risk_level(urgency)
    age = parse_intake_age(intake)
    category = infer_condition_category(symptom=symptom, top_condition=top_condition, age=age)

    historical_serious = count_recent_serious_cases_for_category(user=user, category=category)
    recurrence_count = historical_serious + 1

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

    access_decision.update(
        {
            "category": category,
            "risk_level": risk_level,
            "confidence_score": round(confidence, 2),
            "recurrence_count": recurrence_count,
        }
    )

    if risk_level == SymptomCheckSnapshot.RiskLevel.EMERGENCY:
        access_decision["status"] = "emergency"
        access_decision["message"] = (
            "Emergency risk detected. Community chat is disabled; seek immediate medical care."
        )
        return access_decision

    if confidence < MIN_CONFIDENCE_FOR_AUTO_APPROVAL:
        access_decision["message"] = (
            "Serious risk detected but confidence is below threshold. "
            "Repeat Symptom Checker if symptoms persist."
        )
        return access_decision

    if recurrence_count < MIN_SERIOUS_CASES_FOR_AUTO_APPROVAL:
        access_decision["message"] = (
            f"Serious risk found. Recurrence check is {recurrence_count}/{MIN_SERIOUS_CASES_FOR_AUTO_APPROVAL}; "
            "community tag will generate after recurrence threshold is met."
        )
        return access_decision

    room = get_active_room_for_category(category) or get_active_room_for_category(CATEGORY_GENERAL)
    tag_code = build_community_tag_code(category=category, recurrence_count=recurrence_count)
    tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            category=category,
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    now = timezone.now()
    if tag is None:
        tag = CommunityAccessTag.objects.create(
            user=user,
            tag_code=tag_code,
            category=category,
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

    access_decision.update(
        {
            "status": "approved",
            "tag_code": tag.tag_code,
            "category": category,
            "requires_admin_review": False,
            "message": "Access approved. You can join chat.",
            "community_url": f"/community/room/{room.code}/" if room else "/community/",
        }
    )
    return access_decision


def get_latest_emergency_snapshot(user) -> SymptomCheckSnapshot | None:
    return (
        SymptomCheckSnapshot.objects.filter(
            user=user,
            risk_level=SymptomCheckSnapshot.RiskLevel.EMERGENCY,
        )
        .order_by("-created_at")
        .first()
    )


def build_preview_text(text: str, *, limit: int = 44) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def build_user_community_context(user) -> dict:
    sync_default_community_rooms()

    approved_access_tags = list(
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.APPROVED,
            category__in=ENABLED_COMMUNITY_CATEGORIES,
        ).order_by("-reviewed_at", "-created_at")
    )
    pending_access_tags = list(
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.PENDING,
            category__in=ENABLED_COMMUNITY_CATEGORIES,
        ).order_by("-created_at")
    )
    latest_snapshot = SymptomCheckSnapshot.objects.filter(user=user).order_by("-created_at").first()
    emergency_snapshot = get_latest_emergency_snapshot(user)

    allowed_categories = {tag.category for tag in approved_access_tags}
    rooms = (
        list(CommunityRoom.objects.filter(is_active=True, category__in=allowed_categories).order_by("name"))
        if allowed_categories
        else []
    )

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
                "latest_preview": build_preview_text(
                    latest_message.body if latest_message else "No messages yet."
                ),
                "latest_time": latest_message.created_at if latest_message else None,
            }
        )

    can_access = bool(rooms) and emergency_snapshot is None
    if emergency_snapshot:
        locked_reason = (
            "Emergency severity was detected in your latest serious assessment. "
            "Community access is blocked for safety."
        )
    elif pending_access_tags:
        locked_reason = "Your access tag is pending admin validation."
    elif latest_snapshot is None:
        locked_reason = "Complete a Symptom Checker session to determine eligibility."
    elif latest_snapshot.tag_category not in ENABLED_COMMUNITY_CATEGORIES:
        locked_reason = "Latest assessment does not match available community groups."
    elif not approved_access_tags:
        locked_reason = "No approved access tag yet. Community remains locked."
    else:
        locked_reason = "No active room is available for your approved category."

    return {
        "can_access": can_access,
        "rooms": rooms,
        "room_previews": room_previews,
        "approved_tags": approved_access_tags,
        "pending_tags": pending_access_tags,
        "latest_snapshot": latest_snapshot,
        "locked_reason": locked_reason,
    }


def submit_pending_access_request(user) -> tuple[bool, str]:
    approved = CommunityAccessTag.objects.filter(
        user=user,
        status=CommunityAccessTag.Status.APPROVED,
        category__in=ENABLED_COMMUNITY_CATEGORIES,
    ).exists()
    if approved:
        return True, "Community access is already approved."

    pending_tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.PENDING,
            category__in=ENABLED_COMMUNITY_CATEGORIES,
        )
        .order_by("-created_at")
        .first()
    )
    if not pending_tag:
        return False, "No pending access tag found. Complete Symptom Checker first."

    pending_tag.requested_at = timezone.now()
    pending_tag.save(update_fields=["requested_at", "updated_at"])
    return True, "Community access request submitted for admin validation."


def check_room_access(*, user, room: CommunityRoom) -> tuple[bool, str, CommunityAccessTag | None]:
    if get_latest_emergency_snapshot(user):
        return False, "Community access is blocked due to emergency severity status.", None
    if room.category not in ENABLED_COMMUNITY_CATEGORIES:
        return False, "This room category is disabled.", None

    approved_tag = (
        CommunityAccessTag.objects.filter(
            user=user,
            status=CommunityAccessTag.Status.APPROVED,
            category=room.category,
        )
        .order_by("-reviewed_at", "-created_at")
        .first()
    )
    if not approved_tag:
        return False, "You are not validated for this group category.", None
    return True, "", approved_tag


def validate_chat_message_safety(text: str) -> tuple[bool, str]:
    normalized = (text or "").strip().lower()
    if len(normalized) < 2:
        return False, "Message is too short."

    for phrase in EMERGENCY_CHAT_PHRASES:
        if phrase in normalized:
            return False, "Emergency phrase detected. Please seek emergency care instead of chat."
    for phrase in UNSAFE_ADVICE_PHRASES:
        if phrase in normalized:
            return False, "Unsafe advice detected. Message was blocked for safety."
    return True, ""
