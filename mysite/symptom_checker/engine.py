from __future__ import annotations

from community.services import evaluate_chat_access_eligibility
from symptom_checker.ai_client import AIGenerationError, generate_diagnosis, generate_questions
from symptom_checker.diagnosis import build_result_payload
from symptom_checker.question_flow import add_answer, get_next_index, get_question_at_index
from symptom_checker.schemas import FollowUpQuestion, GivenAnswer, PatientIntake, TriageAssessment
from symptom_checker.services.care_discovery import discover_nearby_care_centers, geocode_location
from symptom_checker.services.recommendations import recommended_articles


FLOW_SESSION_KEY = "symptom_checker_flow"


def create_empty_flow_state() -> dict:
    return {
        "intake": {},
        "questions": [],
        "answers": [],
        "current_index": 0,
        "diagnosis": None,
        "diagnosis_error": "",
        "question_error": "",
        "community_access": None,
        "ai_calls": {"questions": 0, "diagnosis": 0},
    }


def get_flow_state(request) -> dict:
    return request.session.get(FLOW_SESSION_KEY, create_empty_flow_state())


def save_flow_state(request, flow_state: dict) -> None:
    request.session[FLOW_SESSION_KEY] = flow_state
    request.session.modified = True


def start_symptom_session(request, intake: PatientIntake) -> None:
    generated_questions = generate_questions(intake)

    flow_state = create_empty_flow_state()
    flow_state["intake"] = intake.to_dict()
    flow_state["questions"] = [question.to_dict() for question in generated_questions]
    flow_state["answers"] = []
    flow_state["current_index"] = 0
    flow_state["diagnosis"] = None
    flow_state["diagnosis_error"] = ""
    flow_state["question_error"] = ""
    flow_state["community_access"] = None
    flow_state["ai_calls"] = {"questions": 1, "diagnosis": 0}
    save_flow_state(request, flow_state)


def has_active_symptom_session(request) -> bool:
    flow_state = get_flow_state(request)
    return bool(flow_state.get("questions")) and bool(flow_state.get("intake"))


def build_question_page_context(request) -> dict:
    flow_state = get_flow_state(request)
    questions = [FollowUpQuestion.from_dict(row) for row in flow_state.get("questions", [])]
    current_index = int(flow_state.get("current_index", 0))
    current = get_question_at_index(questions, current_index)
    total_questions = len(questions)
    return {
        "has_session": has_active_symptom_session(request),
        "completed": current is None,
        "question": current,
        "step": current_index + 1,
        "total": total_questions,
        "progress": int(((current_index + 1) / total_questions) * 100) if total_questions else 0,
        "questions_source": "ai",
        "question_error": flow_state.get("question_error", ""),
    }


def submit_current_answer(request, answer_value: str) -> bool:
    flow_state = get_flow_state(request)
    questions = [FollowUpQuestion.from_dict(row) for row in flow_state.get("questions", [])]
    answers = [GivenAnswer.from_dict(row) for row in flow_state.get("answers", [])]
    current_index = int(flow_state.get("current_index", 0))
    current = get_question_at_index(questions, current_index)
    if current is None:
        return True

    updated_answers = add_answer(answers, current, answer_value)
    flow_state["answers"] = [answer.to_dict() for answer in updated_answers]
    flow_state["current_index"] = get_next_index(current_index)
    save_flow_state(request, flow_state)
    return flow_state["current_index"] >= len(questions)


def pick_top_condition_names(condition_names: list[str]) -> list[str]:
    return [name.strip() for name in condition_names if name and name.strip()][:3]


def find_nearby_care_centers_for_intake(intake: PatientIntake) -> list[dict]:
    location = (intake.state or "India").strip() or "India"
    return discover_nearby_care_centers(location=location, specialty="", limit=30, radius_m=5000)


def get_or_create_result_payload(request) -> dict:
    flow_state = get_flow_state(request)
    if not has_active_symptom_session(request):
        return {}
    if int(flow_state.get("ai_calls", {}).get("questions", 0)) <= 0:
        message = flow_state.get("question_error") or "AI question generation did not complete."
        raise AIGenerationError(message)

    if flow_state.get("diagnosis"):
        diagnosis_payload = flow_state["diagnosis"]
        diagnosis_error = flow_state.get("diagnosis_error", "")
    else:
        intake = PatientIntake.from_dict(flow_state["intake"])
        answers = [GivenAnswer.from_dict(row) for row in flow_state.get("answers", [])]
        try:
            diagnosis = generate_diagnosis(intake, answers)
            diagnosis_payload = diagnosis.to_dict()
            diagnosis_error = ""
            flow_state["diagnosis"] = diagnosis_payload
            flow_state["ai_calls"]["diagnosis"] = 1
        except AIGenerationError as exc:
            flow_state["diagnosis_error"] = str(exc)
            save_flow_state(request, flow_state)
            raise
        save_flow_state(request, flow_state)

    built = build_result_payload(diagnosis=TriageAssessment.from_dict(diagnosis_payload))

    condition_rows = diagnosis_payload.get("conditions", []) or []
    condition_names = [row.get("name", "") for row in condition_rows if isinstance(row, dict)]
    top_condition_names = pick_top_condition_names(condition_names)
    intake = PatientIntake.from_dict(flow_state.get("intake", {}))

    centers = find_nearby_care_centers_for_intake(intake)
    center_point = geocode_location((intake.state or "").strip())

    built["recommended_centers"] = centers
    built["search_center"] = (
        {
            "latitude": center_point[0],
            "longitude": center_point[1],
            "label": (intake.state or "India").strip() or "India",
            "radius_km": 5,
        }
        if center_point
        else {}
    )
    built["recommended_articles"] = recommended_articles(top_condition_names)
    built["ai_calls"] = flow_state.get("ai_calls", {"questions": 1, "diagnosis": 1})
    built["ai_error"] = diagnosis_error
    built["ai_generation"] = {
        "questions_ai": int(flow_state.get("ai_calls", {}).get("questions", 0)) > 0,
        "diagnosis_ai": int(flow_state.get("ai_calls", {}).get("diagnosis", 0)) > 0,
    }

    if flow_state.get("community_access") is None:
        user = getattr(request, "user", None)
        flow_state["community_access"] = evaluate_chat_access_eligibility(
            user=user,
            intake=intake.to_dict(),
            diagnosis=diagnosis_payload,
        )
        save_flow_state(request, flow_state)

    built["community_access"] = flow_state.get("community_access") or {}
    return built


def reset_symptom_session(request) -> None:
    if FLOW_SESSION_KEY in request.session:
        del request.session[FLOW_SESSION_KEY]
        request.session.modified = True
