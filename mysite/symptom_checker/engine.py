from __future__ import annotations

from symptom_checker.ai_client import AIGenerationError, generate_diagnosis, generate_questions
from symptom_checker.diagnosis import build_result_payload
from symptom_checker.question_flow import append_answer, current_question, next_index
from symptom_checker.schemas import AnswerItem, DiagnosisResult, IntakeData, QuestionItem
from symptom_checker.services.care_discovery import discover_nearby_care_centers, geocode_location
from symptom_checker.services.recommendations import issue_collectible_tag, recommended_articles


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
        "ai_calls": {"questions": 0, "diagnosis": 0},
    }


def _flow(request) -> dict:
    return request.session.get(SESSION_KEY, _initial_state())


def _save_flow(request, flow: dict) -> None:
    request.session[SESSION_KEY] = flow
    request.session.modified = True


def _fallback_questions(intake: IntakeData) -> list[QuestionItem]:
    symptom = (intake.symptom or "your symptom").strip()
    return [
        QuestionItem(
            id=1,
            text=f"When did {symptom} begin?",
            type="single_choice",
            options=["Today", "1-3 days ago", "1-4 weeks ago", "More than 1 month ago"],
        ),
        QuestionItem(id=2, text=f"Is {symptom} getting worse?", type="yesno", options=[]),
        QuestionItem(
            id=3,
            text="How severe is it right now?",
            type="single_choice",
            options=["Mild", "Moderate", "Severe", "Very severe"],
        ),
        QuestionItem(id=4, text="Do you have fever with this issue?", type="yesno", options=[]),
        QuestionItem(id=5, text="Do you have pain along with this issue?", type="yesno", options=[]),
        QuestionItem(id=6, text="Any breathing difficulty right now?", type="yesno", options=[]),
        QuestionItem(id=7, text="Any dizziness, fainting, or confusion?", type="yesno", options=[]),
        QuestionItem(id=8, text="Any active bleeding right now?", type="yesno", options=[]),
        QuestionItem(id=9, text="Any recent injury or accident related to this issue?", type="yesno", options=[]),
        QuestionItem(
            id=10,
            text="Any long-term condition (diabetes, BP, asthma, heart disease)?",
            type="yesno",
            options=[],
        ),
        QuestionItem(id=11, text="Are you currently taking any regular medications?", type="yesno", options=[]),
        QuestionItem(id=12, text="Any known drug or food allergies?", type="yesno", options=[]),
        QuestionItem(id=13, text="Has this happened before?", type="yesno", options=[]),
        QuestionItem(id=14, text="Did symptoms start after food, travel, or outside exposure?", type="yesno", options=[]),
        QuestionItem(id=15, text="Are symptoms affecting normal daily activities?", type="yesno", options=[]),
    ]


def start_session(request, intake: IntakeData) -> None:
    question_error = ""
    try:
        questions = generate_questions(intake)
        question_calls = 1
    except AIGenerationError as exc:
        questions = _fallback_questions(intake)
        question_calls = 0
        question_error = str(exc)

    flow = _initial_state()
    flow["intake"] = intake.to_dict()
    flow["questions"] = [question.to_dict() for question in questions]
    flow["answers"] = []
    flow["current_index"] = 0
    flow["diagnosis"] = None
    flow["diagnosis_error"] = ""
    flow["question_error"] = question_error
    flow["ai_calls"] = {"questions": question_calls, "diagnosis": 0}
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
        "questions_source": "ai" if int(flow.get("ai_calls", {}).get("questions", 0)) > 0 else "fallback",
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
            diagnosis_payload = DiagnosisResult(
                conditions=[],
                urgency="Moderate",
                advice="Assessment unavailable because live AI generation failed. Please retry shortly.",
            ).to_dict()
            diagnosis_error = str(exc)
            flow["diagnosis"] = diagnosis_payload
            flow["diagnosis_error"] = diagnosis_error
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
    built["recommended_specializations"] = []
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

    collectible = issue_collectible_tag()
    if collectible and getattr(collectible, "tag_code", ""):
        built["community_collectible"] = {
            "tag_code": collectible.tag_code,
            "label": collectible.display_label,
            "community_url": f"/community/?tag={collectible.tag_code}",
        }
    else:
        built["community_collectible"] = {}
    return built


def reset_session(request) -> None:
    if SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
        request.session.modified = True
