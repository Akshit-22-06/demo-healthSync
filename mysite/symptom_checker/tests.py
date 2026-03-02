from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from articles.models import Article
from symptom_checker.ai_client import AIGenerationError
from symptom_checker.schemas import DiagnosisCondition, DiagnosisResult, QuestionItem


class SymptomCheckerFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.author = user_model.objects.create_user(
            email="writer@example.com",
            username="writer1",
            password="test-pass-123",
        )
        Article.objects.create(
            title="Skin Infection Care Basics",
            content="Signs of fungal rash, hygiene steps, and when to seek urgent care.",
            author=self.author,
            category="Dermatology",
            status="approved",
            is_published=True,
        )

    @patch("symptom_checker.engine.generate_questions")
    def test_start_creates_session_and_uses_live_question_set(self, mock_generate_questions):
        mock_generate_questions.return_value = [
            QuestionItem(id=1, text="When did symptoms start?", type="text", options=[]),
            QuestionItem(id=2, text="Any fever?", type="yesno", options=[]),
        ]

        response = self.client.post(
            "/symptoms/question/",
            data={
                "age": 21,
                "gender": "Male",
                "state": "Mumbai, Maharashtra, India",
                "symptom": "skin rash",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "When did symptoms start?")

        flow = self.client.session.get("symptom_checker_flow")
        self.assertIsNotNone(flow)
        self.assertEqual(flow["ai_calls"]["questions"], 1)
        self.assertEqual(flow["ai_calls"]["diagnosis"], 0)
        self.assertEqual(len(flow["questions"]), 2)

    @patch("symptom_checker.engine.generate_questions")
    def test_start_falls_back_to_local_questions_on_ai_failure(self, mock_generate_questions):
        mock_generate_questions.side_effect = AIGenerationError("Gemini unavailable")

        response = self.client.post(
            "/symptoms/question/",
            data={
                "age": 20,
                "gender": "Male",
                "state": "Andheri West, Mumbai, Maharashtra, India",
                "symptom": "fungal skin rash itching",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adaptive Symptom Check")

        flow = self.client.session.get("symptom_checker_flow")
        self.assertIsNotNone(flow)
        self.assertEqual(flow["ai_calls"]["questions"], 0)
        self.assertGreaterEqual(len(flow["questions"]), 8)

    @patch("symptom_checker.engine.discover_nearby_care_centers")
    @patch("symptom_checker.engine.generate_diagnosis")
    @patch("symptom_checker.engine.generate_questions")
    def test_result_renders_clinic_hospital_recommendations_on_map(
        self,
        mock_generate_questions,
        mock_generate_diagnosis,
        mock_discover_centers,
    ):
        mock_generate_questions.return_value = [
            QuestionItem(id=1, text="Any fever?", type="yesno", options=[]),
            QuestionItem(id=2, text="Any pain?", type="yesno", options=[]),
        ]
        mock_generate_diagnosis.return_value = DiagnosisResult(
            conditions=[
                DiagnosisCondition(
                    name="Fungal Skin Infection",
                    likelihood="High",
                    reasoning="Persistent itchy rash pattern supports fungal etiology.",
                    specialization="Dermatologist",
                )
            ],
            urgency="Moderate",
            advice="Seek dermatology clinic evaluation within 24 hours.",
        )
        mock_discover_centers.return_value = [
            {
                "name": "City Skin Clinic",
                "specialization": "Dermatologist",
                "facility_type": "clinic",
                "city": "Mumbai",
                "phone": "N/A",
                "email": "N/A",
                "latitude": 19.1136,
                "longitude": 72.8697,
                "distance_km": 2.4,
                "map_search_url": "https://www.openstreetmap.org/",
                "source": "OpenStreetMap",
            }
        ]

        self.client.post(
            "/symptoms/question/",
            data={
                "age": 20,
                "gender": "Male",
                "state": "Andheri West, Mumbai, Maharashtra, India",
                "symptom": "fungal skin rash itching",
            },
        )
        self.client.post("/symptoms/question/", data={"answer": "yes"})
        self.client.post("/symptoms/question/", data={"answer": "no"})
        result_response = self.client.get("/symptoms/result/")

        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, "Nearby Clinics &amp; Hospitals (within 5 km)")
        self.assertContains(result_response, "City Skin Clinic")
        self.assertContains(result_response, "recommended-centers-data")
        self.assertContains(result_response, "Skin Infection Care Basics")

        flow = self.client.session.get("symptom_checker_flow")
        self.assertEqual(flow["ai_calls"]["questions"], 1)
        self.assertEqual(flow["ai_calls"]["diagnosis"], 1)
        self.assertEqual(mock_generate_diagnosis.call_count, 1)

        self.client.get("/symptoms/result/")
        self.assertEqual(mock_generate_diagnosis.call_count, 1)
