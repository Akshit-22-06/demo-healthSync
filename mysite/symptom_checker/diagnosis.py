from __future__ import annotations

from symptom_checker.schemas import TriageAssessment


def build_risk_banner(urgency: str) -> str:
    label = (urgency or "").strip().lower()
    if label == "high":
        return "High-risk pattern detected. Seek urgent medical care now."
    if label == "moderate":
        return "Moderate-risk pattern detected. Arrange a clinic or hospital visit soon."
    return "Low-risk pattern detected. Continue monitoring and seek care if symptoms worsen."


def build_next_24h_plan(urgency: str) -> list[str]:
    label = (urgency or "").strip().lower()
    if label == "high":
        return [
            "Go to the nearest emergency department now; do not delay care.",
            "Avoid self-medication and carry recent reports, prescriptions, and allergy details.",
            "If severe breathing trouble, chest pain, confusion, or bleeding occurs, call emergency services immediately.",
        ]
    if label == "moderate":
        return [
            "Book an in-person clinic or hospital consultation within 24 hours for focused evaluation.",
            "Hydrate, rest, and monitor symptom severity every 4-6 hours.",
            "Escalate to urgent care immediately if red-flag symptoms appear or symptoms rapidly worsen.",
        ]
    return [
        "Continue home care with hydration, adequate rest, and light meals for the next 24 hours.",
        "Track symptoms (fever, pain, breathing, new signs) at least twice today.",
        "Seek clinic care if symptoms persist beyond 24-48 hours or any red-flag symptom appears.",
    ]


def build_health_tips() -> list[str]:
    return [
        "Drink sufficient water or oral fluids unless a clinician advised fluid restriction.",
        "Avoid starting antibiotics, steroids, or painkillers without medical advice.",
        "Prefer simple, non-irritating food and avoid alcohol or tobacco during recovery.",
        "Maintain hand hygiene and use a mask if fever, cough, or infection symptoms are present.",
        "Keep emergency contact and nearby hospital details ready if symptoms escalate.",
    ]


def build_result_payload(*, diagnosis: TriageAssessment) -> dict:
    return {
        "diagnosis": diagnosis.to_dict(),
        "risk_banner": build_risk_banner(diagnosis.urgency),
        "next_24h_plan": build_next_24h_plan(diagnosis.urgency),
        "health_tips": build_health_tips(),
    }
