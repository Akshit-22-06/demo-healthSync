from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from symptom_checker.ai_client import AIGenerationError, generate_symptom_suggestions
from symptom_checker.engine import (
    get_or_build_result,
    has_active_session,
    question_context,
    reset_session,
    start_session,
    submit_answer,
)
from symptom_checker.schemas import IntakeData
from symptom_checker.services.care_discovery import suggest_locations

_COMMON_INDIAN_LOCATIONS = [
    "Ahmedabad, Gujarat",
    "Ankleshwar, Gujarat",
    "Bharuch, Gujarat",
    "Surat, Gujarat",
    "Vadodara, Gujarat",
    "Rajkot, Gujarat",
    "Bhavnagar, Gujarat",
    "Jamnagar, Gujarat",
    "Gandhinagar, Gujarat",
    "Mumbai, Maharashtra",
    "Pune, Maharashtra",
    "Nagpur, Maharashtra",
    "Nashik, Maharashtra",
    "Aurangabad, Maharashtra",
    "Thane, Maharashtra",
    "Delhi",
    "Noida, Uttar Pradesh",
    "Gurugram, Haryana",
    "Ghaziabad, Uttar Pradesh",
    "Lucknow, Uttar Pradesh",
    "Kanpur, Uttar Pradesh",
    "Varanasi, Uttar Pradesh",
    "Jaipur, Rajasthan",
    "Jodhpur, Rajasthan",
    "Udaipur, Rajasthan",
    "Kota, Rajasthan",
    "Bhopal, Madhya Pradesh",
    "Indore, Madhya Pradesh",
    "Gwalior, Madhya Pradesh",
    "Jabalpur, Madhya Pradesh",
    "Bengaluru, Karnataka",
    "Mysuru, Karnataka",
    "Mangaluru, Karnataka",
    "Hubballi, Karnataka",
    "Chennai, Tamil Nadu",
    "Coimbatore, Tamil Nadu",
    "Madurai, Tamil Nadu",
    "Tiruchirappalli, Tamil Nadu",
    "Hyderabad, Telangana",
    "Warangal, Telangana",
    "Nizamabad, Telangana",
    "Kolkata, West Bengal",
    "Howrah, West Bengal",
    "Siliguri, West Bengal",
    "Patna, Bihar",
    "Gaya, Bihar",
    "Ranchi, Jharkhand",
    "Jamshedpur, Jharkhand",
    "Bhubaneswar, Odisha",
    "Cuttack, Odisha",
    "Visakhapatnam, Andhra Pradesh",
    "Vijayawada, Andhra Pradesh",
    "Guntur, Andhra Pradesh",
    "Kochi, Kerala",
    "Thiruvananthapuram, Kerala",
    "Kozhikode, Kerala",
    "Amritsar, Punjab",
    "Ludhiana, Punjab",
    "Chandigarh",
    "Dehradun, Uttarakhand",
    "Shimla, Himachal Pradesh",
    "Srinagar, Jammu and Kashmir",
    "Jammu, Jammu and Kashmir",
    "Guwahati, Assam",
    "Shillong, Meghalaya",
    "Imphal, Manipur",
    "Aizawl, Mizoram",
    "Agartala, Tripura",
    "Gangtok, Sikkim",
    "Panaji, Goa",
    "Puducherry",
]

_COMMON_MEDICAL_TERMS = [
    "fever",
    "viral fever",
    "dengue",
    "malaria",
    "typhoid",
    "cold and cough",
    "sore throat",
    "sinus infection",
    "asthma",
    "bronchitis",
    "pneumonia",
    "chest pain",
    "high blood pressure",
    "diabetes",
    "thyroid disorder",
    "migraine",
    "headache",
    "food poisoning",
    "gastritis",
    "acidity",
    "diarrhea",
    "constipation",
    "kidney stone",
    "urinary infection",
    "skin rash",
    "fungal infection",
    "eczema",
    "psoriasis",
    "acne",
    "allergy",
    "joint pain",
    "arthritis",
    "back pain",
    "neck pain",
    "depression",
    "anxiety",
    "insomnia",
    "hiv",
    "aids",
    "covid-19",
]


def _merge_suggestions(primary: list[str], fallback: list[str], *, max_items: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for source in (primary, fallback):
        for item in source:
            text = (item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= max_items:
                return out
    return out


def start(request):
    if request.method == "POST":
        return redirect("question")
    return render(request, "symptom_checker/start.html")


def question(request):
    if request.method == "POST" and "symptom" in request.POST:
        symptom = (request.POST.get("symptom") or "").strip()
        gender = (request.POST.get("gender") or "").strip()
        state = (request.POST.get("state") or "").strip()
        age_raw = (request.POST.get("age") or "").strip()
        form_data = {"symptom": symptom, "gender": gender or "Male", "state": state, "age": age_raw}
        if not symptom:
            return render(
                request,
                "symptom_checker/start.html",
                {"error_message": "Please enter your main symptom.", "form_data": form_data},
            )

        try:
            age = int(age_raw) if age_raw else None
        except ValueError:
            return render(
                request,
                "symptom_checker/start.html",
                {"error_message": "Age must be a number.", "form_data": form_data},
            )

        intake = IntakeData(age=age, gender=gender, state=state, symptom=symptom)
        try:
            start_session(request, intake)
        except AIGenerationError as exc:
            return render(
                request,
                "symptom_checker/start.html",
                {"error_message": f"Live AI question generation failed: {exc}", "form_data": form_data},
            )
        return redirect("question")

    if request.method == "POST" and "answer" in request.POST:
        if not has_active_session(request):
            return redirect("symptom_home")
        answer_value = (request.POST.get("answer") or "").strip()
        if answer_value:
            is_done = submit_answer(request, answer_value)
            if is_done:
                return redirect("result_page")

    context = question_context(request)
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
            "questions_source": context.get("questions_source", "fallback"),
            "question_error": context.get("question_error", ""),
        },
    )


def result_page(request):
    if not has_active_session(request):
        return redirect("symptom_home")

    result = get_or_build_result(request)
    if not result:
        return redirect("symptom_home")

    diagnosis = result.get("diagnosis", {})
    conditions = diagnosis.get("conditions", [])
    return render(
        request,
        "symptom_checker/result.html",
        {
            "diagnosis": diagnosis,
            "conditions": conditions,
            "urgency": diagnosis.get("urgency", "Moderate"),
            "advice": diagnosis.get("advice", ""),
            "risk_banner": result.get("risk_banner", ""),
            "recommended_centers": result.get("recommended_centers", []),
            "recommended_specializations": result.get("recommended_specializations", []),
            "search_center": result.get("search_center", {}),
            "recommended_articles": result.get("recommended_articles", []),
            "next_24h_plan": result.get("next_24h_plan", []),
            "health_tips": result.get("health_tips", []),
            "collectible": result.get("community_collectible", {}),
            "ai_calls": result.get("ai_calls", {}),
            "ai_error": result.get("ai_error", ""),
        },
    )


def reset_flow(request):
    reset_session(request)
    return redirect(reverse("symptom_home"))


def location_suggest(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"items": []})

    live = suggest_locations(query, limit=40)
    q = query.lower()
    fallback = [loc for loc in _COMMON_INDIAN_LOCATIONS if q in loc.lower()]
    items = _merge_suggestions(live, fallback, max_items=40)
    return JsonResponse({"items": items})


def symptom_suggest(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"items": []})

    q = query.lower()
    fallback = [term for term in _COMMON_MEDICAL_TERMS if q in term.lower()]

    live: list[str] = []
    ai_enabled = bool(getattr(settings, "ENABLE_AI_SYMPTOM_AUTOCOMPLETE", False))
    if ai_enabled and len(query) >= 4 and len(fallback) < 10:
        live = generate_symptom_suggestions(query, max_items=8)

    items = _merge_suggestions(fallback, live, max_items=12)
    return JsonResponse({"items": items})

