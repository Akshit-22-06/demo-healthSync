from __future__ import annotations

import json
import os
import re
import time
from urllib import error as urlerror
from urllib import request as urlrequest

from django.conf import settings

from symptom_checker.schemas import (
    AnswerItem,
    DiagnosisResult,
    IntakeData,
    QuestionItem,
)


class AIGenerationError(RuntimeError):
    pass


def _read_config(name: str, default: str = "") -> str:
    candidates = [os.getenv(name), getattr(settings, name, None), default]
    for raw in candidates:
        value = str(raw or "").strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1].strip()
        if value:
            return value
    return ""


def _parse_json(text: str):
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _retry_delay_seconds(message: str) -> float:
    text = str(message or "")
    patterns = [
        r"retrydelay['\"=: ]+(\d+)\s*s",
        r"retry[^0-9]{0,20}(\d+)\s*seconds",
        r"retry[^0-9]{0,20}(\d+)\s*s",
    ]
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return 0.0


def _generate_content_with_retry(prompt: str, *, retries: int = 2):
    api_key = _read_config("GEMINI_API_KEY")
    model = _read_config("GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        raise AIGenerationError(
            "Gemini API key missing. Set GEMINI_API_KEY in .env and restart server."
        )

    last_error = None
    for attempt in range(retries + 1):
        try:
            return _call_gemini(prompt=prompt, api_key=api_key, model=model)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                delay = max(0.8 * (attempt + 1), _retry_delay_seconds(str(exc)))
                time.sleep(min(delay, 20.0))
    raise AIGenerationError(_friendly_error(last_error))


def _call_gemini(*, prompt: str, api_key: str, model: str) -> str:
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Return strictly valid JSON only. No markdown, no prose, no code fences.\n\n"
                            + prompt
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.05,
            "topP": 0.2,
            "responseMimeType": "application/json",
        },
    }
    req = urlrequest.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    content = ""
    for part in parts:
        text = (part.get("text") or "").strip()
        if text:
            content += text
    if not content:
        raise RuntimeError("Gemini returned empty content.")
    return content


def _friendly_error(exc: Exception | None) -> str:
    message = str(exc or "")
    lowered = message.lower()
    if "not found for api version" in lowered or "is not found" in lowered or "404" in lowered:
        return (
            "Gemini model name is invalid/unsupported for this endpoint. "
            "Use GEMINI_MODEL=gemini-2.5-flash."
        )
    if "reported as leaked" in lowered or "api key was reported as leaked" in lowered:
        return (
            "Gemini rejected this key because it was reported as leaked. "
            "Generate a new Gemini API key and replace GEMINI_API_KEY."
        )
    if "quota" in lowered or "429" in lowered or "rate limit" in lowered:
        retry_match = re.search(r"retry[^0-9]*(\d+)", message)
        retry_hint = f" Retry in about {retry_match.group(1)} seconds." if retry_match else ""
        return "Gemini rate/quota limit reached (429). Retry shortly." + retry_hint
    if "invalid api key" in lowered or "incorrect api key" in lowered or "401" in lowered:
        return "Gemini API key is invalid or unauthorized (401). Update GEMINI_API_KEY and restart server."
    if "permission" in lowered or "forbidden" in lowered or "403" in lowered:
        return "Gemini request forbidden (403). Check key permissions, API enablement, and model access."
    return "Gemini request failed. Check GEMINI_API_KEY, model name, and quota."


def _validate_question(row: dict, idx: int) -> QuestionItem:
    text = str(row.get("text") or "").strip()
    q_type = str(row.get("type") or "yesno").strip().lower()
    options = row.get("options") or []
    if not isinstance(options, list):
        options = []

    item = QuestionItem(
        id=idx,
        text=text,
        type=q_type,
        options=[str(opt).strip() for opt in options if str(opt).strip()],
    )
    if not item.text:
        raise AIGenerationError("AI returned an empty question.")
    if item.type not in {"yesno", "text", "single_choice"}:
        raise AIGenerationError(f"AI returned unsupported question type: {item.type}")
    if item.type == "single_choice":
        if len(item.options) < 2 or len(item.options) > 4:
            raise AIGenerationError("AI single_choice question must include 2-4 options.")
    else:
        item.options = []
    return item

def generate_questions(intake: IntakeData) -> list[QuestionItem]:
    prompt = f"""
You are a medical triage intake engine for first-pass risk stratification, not final diagnosis.
Generate exactly 15 medically relevant follow-up questions for this profile.

Output rules:
1) Return ONLY a JSON array with exactly 15 objects.
2) Each object must contain keys: id, text, type, options, ai_generated.
3) ai_generated must be true.
4) type must be one of: yesno, text, single_choice.
5) For yesno/text, options must be [].
6) For single_choice, options must have 2 to 4 concise choices.
7) No duplicate questions, no greetings, no explanations.

Clinical coverage across the 15 questions must include:
- Onset and duration
- Progression and severity
- Red flags (bleeding, breathing difficulty, altered sensorium, severe pain)
- Associated symptoms
- Exposure/travel/contact risks
- Relevant comorbidity and medication context
- Prior episodes and functional impact

Question style:
- One clinical concept per question
- Max 16 words per question
- Neutral, non-judgmental language
- Do not assume a confirmed diagnosis

User profile:
Age: {intake.age}
Gender: {intake.gender}
Location: {intake.state}
Primary symptom text: {intake.symptom}
"""

    response = _generate_content_with_retry(prompt, retries=3)
    try:
        parsed = _parse_json(response)
    except Exception as exc:
        raise AIGenerationError(f"Could not parse AI questions JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise AIGenerationError("AI questions response must be a JSON array.")
    if len(parsed) != 15:
        raise AIGenerationError("AI must return exactly 15 questions.")

    questions: list[QuestionItem] = []
    seen: set[str] = set()
    for idx, row in enumerate(parsed, start=1):
        if not isinstance(row, dict):
            raise AIGenerationError("AI question items must be JSON objects.")
        if row.get("ai_generated") is not True:
            raise AIGenerationError("AI generation marker missing for question item.")
        question = _validate_question(row, idx)
        signature = question.text.lower()
        if signature in seen:
            raise AIGenerationError("AI returned duplicate questions.")
        seen.add(signature)
        questions.append(question)
    return questions


def generate_diagnosis(intake: IntakeData, answers: list[AnswerItem]) -> DiagnosisResult:
    answer_lines = "\n".join(f"- Q: {answer.question_text} | A: {answer.answer}" for answer in answers)
    prompt = f"""
You are a conservative clinical triage assistant for informational risk guidance.
Do NOT provide definitive diagnosis. Provide structured differential and urgency triage.

Return ONLY a JSON object with this exact schema:
{{
  "conditions": [
    {{
      "name": "Condition name",
      "likelihood": "High | Medium | Low",
      "reasoning": "One concise, evidence-linked sentence",
      "specialization": "Most relevant clinician specialty"
    }}
  ],
  "urgency": "Low | Moderate | High",
  "advice": "Actionable next-step guidance with red-flag escalation",
  "ai_generated": true
}}

Strict clinical rules:
1) Return 2 to 4 plausible conditions only.
2) At least one condition must directly explain primary symptom.
3) Use High likelihood only when multiple answers strongly support it.
4) urgency=High only for red-flag patterns (e.g., breathing distress, active bleeding, severe neurologic signs).
5) reasoning must reference observed symptom pattern, not guesswork.
6) advice must be practical and safety-focused; include when to seek urgent care.
7) No markdown, no narrative outside schema, no null values.

User profile:
Age: {intake.age}
Gender: {intake.gender}
Location: {intake.state}
Primary symptom text: {intake.symptom}

Follow-up answers:
{answer_lines}
"""

    response = _generate_content_with_retry(prompt)
    try:
        parsed = _parse_json(response)
    except Exception as exc:
        raise AIGenerationError(f"Could not parse AI diagnosis JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise AIGenerationError("AI diagnosis response must be a JSON object.")
    if parsed.get("ai_generated") is not True:
        raise AIGenerationError("AI generation marker missing for diagnosis.")

    diagnosis = DiagnosisResult.from_dict(parsed)
    diagnosis.conditions = [c for c in diagnosis.conditions if c.name.strip()]
    if not diagnosis.conditions:
        raise AIGenerationError("AI diagnosis returned no valid conditions.")
    if diagnosis.urgency not in {"Low", "Moderate", "High"}:
        raise AIGenerationError("AI diagnosis returned invalid urgency.")
    if not diagnosis.advice.strip():
        raise AIGenerationError("AI diagnosis returned empty advice.")
    return diagnosis


def generate_symptom_suggestions(query: str, *, max_items: int = 10) -> list[str]:
    cleaned = (query or "").strip()
    if len(cleaned) < 2:
        return []

    max_items = max(3, min(int(max_items or 10), 20))
    prompt = f"""
You generate health search suggestions for an input field.
Return ONLY a JSON array (no markdown) of up to {max_items} short terms.
Use clinically common symptom/condition names only.
Input text: {cleaned}
"""

    try:
        response = _generate_content_with_retry(prompt, retries=1)
        parsed = _parse_json(response)
    except Exception as exc:
        raise AIGenerationError(str(exc)) from exc

    if not isinstance(parsed, list):
        raise AIGenerationError("AI symptom suggestion response is not a JSON array.")

    out: list[str] = []
    seen: set[str] = set()
    for row in parsed:
        item = str(row or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out

