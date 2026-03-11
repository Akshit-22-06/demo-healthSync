from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from community.models import CommunityMessage, CommunityRoom
from community.services import (
    build_user_community_context,
    check_room_access,
    submit_pending_access_request,
    validate_chat_message_safety,
)


UNLOCK_NOTICE_KEY_PREFIX = "community_unlocked_notice_seen_"


@login_required(login_url="/login/")
@never_cache
def community_home(request):
    context = build_user_community_context(request.user)
    notice_key = f"{UNLOCK_NOTICE_KEY_PREFIX}{request.user.pk}"
    show_unlocked_notice = bool(context.get("can_access")) and not bool(request.session.get(notice_key))
    context["show_unlocked_notice"] = show_unlocked_notice
    if show_unlocked_notice:
        request.session[notice_key] = True
        request.session.modified = True
    return render(request, "community/community.html", context)


@login_required(login_url="/login/")
def submit_community_access_request(request):
    if request.method != "POST":
        return redirect("community")

    ok, info = submit_pending_access_request(request.user)
    if ok:
        messages.success(request, info)
    else:
        messages.error(request, info)
    return redirect("community")


@login_required(login_url="/login/")
@never_cache
def community_room_view(request, room_code: str):
    room = get_object_or_404(CommunityRoom, code=room_code, is_active=True)
    has_access, access_error, access_tag = check_room_access(user=request.user, room=room)
    if not has_access:
        messages.error(request, access_error)
        return redirect("community")

    if request.method == "POST":
        body = (request.POST.get("message") or "").strip()
        if body:
            is_allowed, reason = validate_chat_message_safety(body)
            if is_allowed:
                CommunityMessage.objects.create(room=room, user=request.user, body=body)
            else:
                CommunityMessage.objects.create(
                    room=room,
                    user=request.user,
                    body=body,
                    is_blocked=True,
                    is_flagged=True,
                    moderation_reason=reason,
                )
                messages.error(request, reason)
        return redirect("community_room", room_code=room.code)

    messages_qs = CommunityMessage.objects.filter(room=room, is_blocked=False).select_related("user")
    context = build_user_community_context(request.user)
    context.update(
        {
            "room": room,
            "room_messages": messages_qs,
            "access_tag": access_tag,
        }
    )
    return render(request, "community/room.html", context)
