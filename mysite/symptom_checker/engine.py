from __future__ import annotations

from community.services import evaluate_community_eligibility
from symptom_checker.ai_client import AIGenerationError, generate_diagnosis, generate_questions
from symptom_checker.diagnosis import build_result_payload
from symptom_checker.question_flow import append_answer, current_question, next_index
from symptom_checker.schemas import AnswerItem, DiagnosisResult, IntakeData, QuestionItem
from symptom_checker.services.care_discovery import discover_nearby_care_centers, geocode_location
from symptom_checker.services.recommendations import recommended_articles


SESSION_KEY = "symptom_checker_flow"


def _initial_state() -> dict:
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


def _flow(request) -> dict:
    return request.session.get(SESSION_KEY, _initial_state())


def _save_flow(request, flow: dict) -> None:
    request.session[SESSION_KEY] = flow
    request.session.modified = True


def start_session(request, intake: IntakeData) -> None:
    questions = generate_questions(intake)

    flow = _initial_state()
    flow["intake"] = intake.to_dict()
    flow["questions"] = [question.to_dict() for question in questions]
    flow["answers"] = []
    flow["current_index"] = 0
    flow["diagnosis"] = None
    flow["diagnosis_error"] = ""
    flow["question_error"] = ""
    flow["community_access"] = None
    flow["ai_calls"] = {"questions": 1, "diagnosis": 0}
    _save_flow(request, flow)


def has_active_session(request) -> bool:
    flow = _flow(request)
    return bool(flow.get("questions")) and bool(flow.get("intake"))


def question_context(request) -> dict:
    flow = _flow(request)
    questions = [QuestionItem.from_dict(row) for row in flow.get("questions", [])]
    idx = int(flow.get("current_index", 0))
    question = current_question(questions, idx)
    total = len(questions)
    return {
        "has_session": has_active_session(request),
        "completed": question is None,
        "question": question,
        "step": idx + 1,
        "total": total,
        "progress": int(((idx + 1) / total) * 100) if total else 0,
        "questions_source": "ai",
        "question_error": flow.get("question_error", ""),
    }


def submit_answer(request, answer_value: str) -> bool:
    flow = _flow(request)
    questions = [QuestionItem.from_dict(row) for row in flow.get("questions", [])]
    answers = [AnswerItem.from_dict(row) for row in flow.get("answers", [])]
    idx = int(flow.get("current_index", 0))
    question = current_question(questions, idx)
    if question is None:
        return True

    updated_answers = append_answer(answers, question, answer_value)
    flow["answers"] = [answer.to_dict() for answer in updated_answers]
    flow["current_index"] = next_index(idx)
    _save_flow(request, flow)
    return flow["current_index"] >= len(questions)


def _top_conditions_from_diagnosis(condition_names: list[str]) -> list[str]:
    return [name.strip() for name in condition_names if name and name.strip()][:3]


def _nearby_centers_for_location(intake: IntakeData) -> list[dict]:
    location = (intake.state or "India").strip() or "India"
    return discover_nearby_care_centers(location=location, specialty="", limit=30, radius_m=5000)


def get_or_build_result(request) -> dict:
    flow = _flow(request)
    if not has_active_session(request):
        return {}
    if int(flow.get("ai_calls", {}).get("questions", 0)) <= 0:
        raise AIGenerationError(flow.get("question_error") or "AI question generation did not complete.")

    if flow.get("diagnosis"):
        diagnosis_payload = flow["diagnosis"]
        diagnosis_error = flow.get("diagnosis_error", "")
    else:
        intake = IntakeData.from_dict(flow["intake"])
        answers = [AnswerItem.from_dict(row) for row in flow.get("answers", [])]
        try:
            diagnosis = generate_diagnosis(intake, answers)
            diagnosis_payload = diagnosis.to_dict()
            diagnosis_error = ""
            flow["diagnosis"] = diagnosis_payload
            flow["ai_calls"]["diagnosis"] = 1
        except AIGenerationError as exc:
            flow["diagnosis_error"] = str(exc)
            _save_flow(request, flow)
            raise
        _save_flow(request, flow)

    built = build_result_payload(diagnosis=DiagnosisResult.from_dict(diagnosis_payload))

    condition_rows = diagnosis_payload.get("conditions", []) or []
    top_condition_names = _top_conditions_from_diagnosis(
        [row.get("name", "") for row in condition_rows if isinstance(row, dict)]
    )
    intake = IntakeData.from_dict(flow.get("intake", {}))

    centers = _nearby_centers_for_location(intake)
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
    built["ai_calls"] = flow.get("ai_calls", {"questions": 1, "diagnosis": 1})
    built["ai_error"] = diagnosis_error
    built["ai_generation"] = {
        "questions_ai": int(flow.get("ai_calls", {}).get("questions", 0)) > 0,
        "diagnosis_ai": int(flow.get("ai_calls", {}).get("diagnosis", 0)) > 0,
    }

    if flow.get("community_access") is None:
        user = getattr(request, "user", None)
        flow["community_access"] = evaluate_community_eligibility(
            user=user,
            intake=intake.to_dict(),
            diagnosis=diagnosis_payload,
        )
        _save_flow(request, flow)

    built["community_access"] = flow.get("community_access") or {}
    return built


def reset_session(request) -> None:
    if SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
        request.session.modified = True
