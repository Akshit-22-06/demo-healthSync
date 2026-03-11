from __future__ import annotations

import json
import os
import re
import time
from difflib import SequenceMatcher
from urllib import error as urlerror
from urllib import request as urlrequest

from django.conf import settings

from symptom_checker.schemas import (
    FollowUpQuestion,
    GivenAnswer,
    PatientIntake,
    TriageAssessment,
)
from symptom_checker.text_assets import (
    FALLBACK_SYMPTOM_TERMS,
    MAX_AUTO_RETRY_WAIT_SECONDS,
    build_diagnosis_generation_prompt,
    build_question_generation_prompt,
    build_symptom_suggestion_prompt,
)


class AIGenerationError(RuntimeError):
    pass

def _read_setting(name: str, default: str = "") -> str:
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


def _parse_json_response(text: str):
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _extract_retry_seconds(message: str) -> float:
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
    api_key = _read_setting("GEMINI_SC_KEY")
    model = _read_setting("GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        raise AIGenerationError(
            "Gemini API key missing. Set GEMINI_SC_KEY in .env and restart server."
        )

    last_error = None
    for attempt in range(retries + 1):
        try:
            return _call_gemini_api(prompt=prompt, api_key=api_key, model=model)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                server_retry_delay = _extract_retry_seconds(str(exc))
                # If server asks for a long retry window, avoid hammering the API.
                if server_retry_delay > MAX_AUTO_RETRY_WAIT_SECONDS:
                    break
                if server_retry_delay > 0:
                    delay = server_retry_delay
                else:
                    delay = 0.8 * (attempt + 1)
                time.sleep(min(delay, MAX_AUTO_RETRY_WAIT_SECONDS))
    raise AIGenerationError(_build_user_friendly_error(last_error))


def _call_gemini_api(*, prompt: str, api_key: str, model: str) -> str:
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


def _build_user_friendly_error(exc: Exception | None) -> str:
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
            "Generate a new Gemini API key and replace GEMINI_SC_KEY."
        )
    if "quota" in lowered or "429" in lowered or "rate limit" in lowered:
        retry_match = re.search(r"retry[^0-9]*(\d+)", message)
        retry_hint = f" Retry in about {retry_match.group(1)} seconds." if retry_match else ""
        zero_quota_hints = (
            "limit '0'",
            "limit: 0",
            '"limit":"0"',
            '"limit": "0"',
            "quota value is 0",
            "quota_limit_value",
        )
        if any(hint in lowered for hint in zero_quota_hints):
            return (
                "Gemini quota is configured as 0 for this project/model (429). "
                "Changing API keys in the same project will not help. "
                "Enable billing or use a project/model with available quota."
                + retry_hint
            )
        return "Gemini rate/quota limit reached (429). Retry shortly." + retry_hint
    if "invalid api key" in lowered or "incorrect api key" in lowered or "401" in lowered:
        return "Gemini API key is invalid or unauthorized (401). Update GEMINI_SC_KEY and restart server."
    if "permission" in lowered or "forbidden" in lowered or "403" in lowered:
        return "Gemini request forbidden (403). Check key permissions, API enablement, and model access."
    return "Gemini request failed. Check GEMINI_SC_KEY, model name, and quota."


def _normalize_search_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower()).strip()


def fallback_symptom_suggestions(query: str, *, max_items: int = 10) -> list[str]:
    cleaned = (query or "").strip()
    if len(cleaned) < 2:
        return []

    max_items = max(3, min(int(max_items or 10), 20))
    q = _normalize_search_text(cleaned)
    starts: list[tuple[float, str]] = []
    contains: list[tuple[float, str]] = []
    fuzzy: list[tuple[float, str]] = []

    for item in FALLBACK_SYMPTOM_TERMS:
        key = _normalize_search_text(item)
        if not key:
            continue
        if key.startswith(q):
            starts.append((1.0, item))
            continue
        if q in key:
            contains.append((0.9, item))
            continue
        ratio = SequenceMatcher(a=q, b=key).ratio()
        if ratio >= 0.45:
            fuzzy.append((ratio, item))

    fuzzy.sort(key=lambda row: row[0], reverse=True)
    ordered = starts + contains + fuzzy

    out: list[str] = []
    seen: set[str] = set()
    for _, item in ordered:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def _build_question_from_ai_row(row: dict, idx: int) -> FollowUpQuestion:
    text = str(row.get("text") or "").strip()
    q_type = str(row.get("type") or "yesno").strip().lower()
    options = row.get("options") or []
    if not isinstance(options, list):
        options = []

    item = FollowUpQuestion(
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

def generate_questions(intake: PatientIntake) -> list[FollowUpQuestion]:
    prompt = build_question_generation_prompt(intake)
    response = _generate_content_with_retry(prompt, retries=3)
    try:
        parsed = _parse_json_response(response)
    except Exception as exc:
        raise AIGenerationError(f"Could not parse AI questions JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise AIGenerationError("AI questions response must be a JSON array.")
    if len(parsed) != 15:
        raise AIGenerationError("AI must return exactly 15 questions.")

    questions: list[FollowUpQuestion] = []
    seen: set[str] = set()
    for idx, row in enumerate(parsed, start=1):
        if not isinstance(row, dict):
            raise AIGenerationError("AI question items must be JSON objects.")
        if row.get("ai_generated") is not True:
            raise AIGenerationError("AI generation marker missing for question item.")
        question = _build_question_from_ai_row(row, idx)
        signature = question.text.lower()
        if signature in seen:
            raise AIGenerationError("AI returned duplicate questions.")
        seen.add(signature)
        questions.append(question)
    return questions


def generate_diagnosis(intake: PatientIntake, answers: list[GivenAnswer]) -> TriageAssessment:
    prompt = build_diagnosis_generation_prompt(intake, answers)
    response = _generate_content_with_retry(prompt)
    try:
        parsed = _parse_json_response(response)
    except Exception as exc:
        raise AIGenerationError(f"Could not parse AI diagnosis JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise AIGenerationError("AI diagnosis response must be a JSON object.")
    if parsed.get("ai_generated") is not True:
        raise AIGenerationError("AI generation marker missing for diagnosis.")

    diagnosis = TriageAssessment.from_dict(parsed)
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
    fallback_items = fallback_symptom_suggestions(cleaned, max_items=max_items)
    # Preserve Gemini quota for core triage calls by using deterministic suggestions first.
    if fallback_items:
        return fallback_items[:max_items]
    if len(cleaned) < 4:
        return []

    prompt = build_symptom_suggestion_prompt(cleaned, max_items)

    ai_items: list[str] = []
    try:
        response = _generate_content_with_retry(prompt, retries=1)
        parsed = _parse_json_response(response)
        if isinstance(parsed, list):
            for row in parsed:
                item = str(row or "").strip()
                if item and len(item) <= 64:
                    ai_items.append(item)
    except Exception:
        ai_items = []

    out: list[str] = []
    seen: set[str] = set()
    for item in ai_items + fallback_items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out
