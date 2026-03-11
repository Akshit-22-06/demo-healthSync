from __future__ import annotations

from symptom_checker.schemas import FollowUpQuestion, GivenAnswer


def get_question_at_index(
    questions: list[FollowUpQuestion], current_index: int
) -> FollowUpQuestion | None:
    if current_index < 0 or current_index >= len(questions):
        return None
    return questions[current_index]


def add_answer(
    answers: list[GivenAnswer], question: FollowUpQuestion, answer_value: str
) -> list[GivenAnswer]:
    updated = list(answers)
    updated.append(
        GivenAnswer(
            question_id=question.id,
            question_text=question.text,
            answer=answer_value,
        )
    )
    return updated


def get_next_index(current_index: int) -> int:
    return current_index + 1
