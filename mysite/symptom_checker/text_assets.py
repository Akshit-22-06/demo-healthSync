from __future__ import annotations

from symptom_checker.schemas import GivenAnswer, PatientIntake


MAX_AUTO_RETRY_WAIT_SECONDS = 45.0

FALLBACK_SYMPTOM_TERMS: tuple[str, ...] = (
    "Abdominal pain",
    "Acne",
    "Allergic rhinitis",
    "Anxiety disorder",
    "Asthma",
    "Back pain",
    "Bipolar disorder",
    "Bronchitis",
    "Chest pain",
    "Chronic kidney disease",
    "Common cold",
    "Conjunctivitis",
    "Constipation",
    "COPD",
    "Depression",
    "Diabetes mellitus",
    "Diarrhea",
    "Dizziness",
    "Down syndrome",
    "Eczema",
    "Fever",
    "Flu",
    "Food poisoning",
    "Fungal skin infection",
    "Gastritis",
    "GERD",
    "Headache",
    "Heart failure",
    "Hypertension",
    "Hyperthyroidism",
    "Hypothyroidism",
    "Insomnia",
    "Irritable bowel syndrome",
    "Migraine",
    "Nausea",
    "Otitis media",
    "PCOS",
    "Pneumonia",
    "Psoriasis",
    "Schizophrenia",
    "Sinusitis",
    "Skin rash",
    "Sore throat",
    "Stress disorder",
    "Type 1 diabetes",
    "Type 2 diabetes",
    "Urinary tract infection",
    "Viral infection",
    "Vomiting",
)


def build_question_generation_prompt(intake: PatientIntake) -> str:
    return f"""
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


def build_diagnosis_generation_prompt(intake: PatientIntake, answers: list[GivenAnswer]) -> str:
    answer_lines = "\n".join(f"- Q: {answer.question_text} | A: {answer.answer}" for answer in answers)
    return f"""
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


def build_symptom_suggestion_prompt(cleaned_query: str, max_items: int) -> str:
    return f"""
You generate health search suggestions for an input field.
Return ONLY a JSON array (no markdown) of up to {max_items} short terms.
Use clinically common symptom/condition names only.
Input text: {cleaned_query}
"""
