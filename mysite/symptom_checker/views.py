from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from symptom_checker.ai_client import (
    AIGenerationError,
    fallback_symptom_suggestions,
    generate_symptom_suggestions,
)
from symptom_checker.engine import (
    FLOW_SESSION_KEY,
    build_question_page_context,
    get_or_create_result_payload,
    has_active_symptom_session,
    reset_symptom_session,
    start_symptom_session,
    submit_current_answer,
)
from symptom_checker.schemas import PatientIntake
from symptom_checker.services.care_discovery import suggest_locations


GUEST_SC_USED_KEY = "symptom_checker_guest_used_once"


def is_guest_limit_reached(request) -> bool:
    is_logged_in = getattr(request.user, "is_authenticated", False)
    return (not is_logged_in) and bool(request.session.get(GUEST_SC_USED_KEY))


def get_guest_limit_message(request) -> str:
    if is_guest_limit_reached(request):
        return "Guest access allows one Symptom Checker run. Please login to continue."
    return ""


def render_start_page(request, *, error_message: str = "", form_data: dict | None = None):
    context = {}
    if error_message:
        context["error_message"] = error_message
    if form_data:
        context["form_data"] = form_data
    guest_limit_message = get_guest_limit_message(request)
    if guest_limit_message:
        context["guest_limit_message"] = guest_limit_message
    return render(request, "symptom_checker/start.html", context)


def read_intake_form_data(request) -> dict[str, str]:
    symptom = (request.POST.get("symptom") or "").strip()
    gender = (request.POST.get("gender") or "").strip()
    state = (request.POST.get("state") or "").strip()
    age = (request.POST.get("age") or "").strip()
    return {
        "symptom": symptom,
        "gender": gender or "Male",
        "state": state,
        "age": age,
    }


def validate_intake_form(form_data: dict[str, str]) -> tuple[PatientIntake | None, str]:
    symptom = form_data["symptom"]
    state = form_data["state"]
    age_raw = form_data["age"]
    gender = form_data["gender"]

    if not symptom:
        return None, "Please enter your main symptom."
    if not state:
        return None, "Please enter your location."

    try:
        age = int(age_raw) if age_raw else None
    except ValueError:
        return None, "Age must be a number."

    intake = PatientIntake(age=age, gender=gender, state=state, symptom=symptom)
    return intake, ""


def start(request):
    if request.method == "POST":
        return redirect("question")
    return render_start_page(request)


def question(request):
    if request.method == "POST" and "symptom" in request.POST:
        form_data = read_intake_form_data(request)

        if is_guest_limit_reached(request):
            return render_start_page(
                request,
                error_message="Login is required for another Symptom Checker run.",
                form_data=form_data,
            )

        intake, validation_error = validate_intake_form(form_data)
        if validation_error:
            return render_start_page(request, error_message=validation_error, form_data=form_data)

        try:
            start_symptom_session(request, intake)
        except AIGenerationError as exc:
            return render_start_page(
                request,
                error_message=f"AI generation failed ({exc}). Please run Symptom Checker again.",
                form_data=form_data,
            )
        return redirect("question")

    if request.method == "POST" and "answer" in request.POST:
        if not has_active_symptom_session(request):
            if is_guest_limit_reached(request):
                return render_start_page(request)
            return redirect("symptom_home")

        answer_value = (request.POST.get("answer") or "").strip()
        if answer_value:
            is_done = submit_current_answer(request, answer_value)
            if is_done:
                return redirect("result_page")

    context = build_question_page_context(request)
    if not context["has_session"]:
        return redirect("symptom_home")
    if context["completed"]:
        return redirect("result_page")

    return render(
        request,
        "symptom_checker/question.html",
        {
            "question": context["question"],
            "step": context["step"],
            "total": context["total"],
            "progress": context["progress"],
            "questions_source": context.get("questions_source", "ai"),
            "question_error": context.get("question_error", ""),
        },
    )


def result_page(request):
    if not has_active_symptom_session(request):
        if is_guest_limit_reached(request):
            return render_start_page(request)
        return redirect("symptom_home")

    try:
        result = get_or_create_result_payload(request)
    except AIGenerationError as exc:
        flow_state = request.session.get(FLOW_SESSION_KEY, {})
        intake_data = flow_state.get("intake", {}) if isinstance(flow_state, dict) else {}
        form_data = {
            "age": intake_data.get("age") or "",
            "gender": intake_data.get("gender") or "Male",
            "state": intake_data.get("state") or "",
            "symptom": intake_data.get("symptom") or "",
        }
        reset_symptom_session(request)
        return render_start_page(
            request,
            error_message=f"AI generation failed ({exc}). Please run Symptom Checker again.",
            form_data=form_data,
        )

    if not result:
        return redirect("symptom_home")

    if not getattr(request.user, "is_authenticated", False):
        request.session[GUEST_SC_USED_KEY] = True
        request.session.modified = True

    diagnosis = result.get("diagnosis", {})
    return render(
        request,
        "symptom_checker/result.html",
        {
            "diagnosis": diagnosis,
            "conditions": diagnosis.get("conditions", []),
            "urgency": diagnosis.get("urgency", "Moderate"),
            "advice": diagnosis.get("advice", ""),
            "risk_banner": result.get("risk_banner", ""),
            "recommended_centers": result.get("recommended_centers", []),
            "search_center": result.get("search_center", {}),
            "recommended_articles": result.get("recommended_articles", []),
            "next_24h_plan": result.get("next_24h_plan", []),
            "health_tips": result.get("health_tips", []),
            "community_access": result.get("community_access", {}),
            "ai_generation": result.get("ai_generation", {}),
            "ai_calls": result.get("ai_calls", {}),
            "ai_error": result.get("ai_error", ""),
        },
    )


def reset_flow(request):
    reset_symptom_session(request)
    return redirect(reverse("symptom_home"))


def location_suggest(request):
    query = request.GET.get("q", "")
    return JsonResponse({"items": suggest_locations(query, limit=10)})


def symptom_suggest(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"items": []})

    try:
        items = generate_symptom_suggestions(query, max_items=10)
    except Exception:
        items = fallback_symptom_suggestions(query, max_items=10)
    return JsonResponse({"items": items})
