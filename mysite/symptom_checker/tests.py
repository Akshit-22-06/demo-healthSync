from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from articles.models import Article
from symptom_checker.ai_client import AIGenerationError, generate_symptom_suggestions
from symptom_checker.schemas import PossibleCondition, TriageAssessment, FollowUpQuestion


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
            FollowUpQuestion(id=1, text="When did symptoms start?", type="text", options=[]),
            FollowUpQuestion(id=2, text="Any fever?", type="yesno", options=[]),
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
    def test_start_returns_to_sc_when_ai_question_generation_fails(self, mock_generate_questions):
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
        self.assertContains(response, "Please run Symptom Checker again.")

        flow = self.client.session.get("symptom_checker_flow")
        self.assertFalse(flow)

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
            FollowUpQuestion(id=1, text="Any fever?", type="yesno", options=[]),
            FollowUpQuestion(id=2, text="Any pain?", type="yesno", options=[]),
        ]
        mock_generate_diagnosis.return_value = TriageAssessment(
            conditions=[
                PossibleCondition(
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

    @patch("symptom_checker.engine.generate_diagnosis")
    @patch("symptom_checker.engine.generate_questions")
    def test_result_redirects_to_sc_when_ai_diagnosis_fails(self, mock_generate_questions, mock_generate_diagnosis):
        mock_generate_questions.return_value = [
            FollowUpQuestion(id=1, text="Any fever?", type="yesno", options=[]),
        ]
        mock_generate_diagnosis.side_effect = AIGenerationError("quota exceeded")

        self.client.post(
            "/symptoms/question/",
            data={
                "age": 20,
                "gender": "Male",
                "state": "Mumbai, Maharashtra, India",
                "symptom": "down syndrome",
            },
        )
        self.client.post("/symptoms/question/", data={"answer": "yes"})
        response = self.client.get("/symptoms/result/", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please run Symptom Checker again.")
        self.assertContains(response, "AI generation failed")

    @patch("symptom_checker.views.suggest_locations")
    def test_location_suggest_endpoint_returns_api_items(self, mock_suggest_locations):
        mock_suggest_locations.return_value = ["Andheri West, Mumbai, Maharashtra"]
        response = self.client.get("/symptoms/location-suggest/?q=andheri")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"items": ["Andheri West, Mumbai, Maharashtra"]})

    @patch("symptom_checker.views.generate_symptom_suggestions")
    def test_symptom_suggest_endpoint_returns_ai_items(self, mock_generate_symptom_suggestions):
        mock_generate_symptom_suggestions.return_value = ["Down syndrome"]
        response = self.client.get("/symptoms/symptom-suggest/?q=down")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"items": ["Down syndrome"]})

    @patch("symptom_checker.views.generate_symptom_suggestions")
    def test_symptom_suggest_endpoint_uses_fallback_when_generator_fails(self, mock_generate_symptom_suggestions):
        mock_generate_symptom_suggestions.side_effect = RuntimeError("upstream failure")
        response = self.client.get("/symptoms/symptom-suggest/?q=down")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)
        self.assertIn("Down syndrome", payload["items"])

    @patch("symptom_checker.engine.discover_nearby_care_centers")
    @patch("symptom_checker.engine.generate_diagnosis")
    @patch("symptom_checker.engine.generate_questions")
    def test_guest_can_run_sc_once_then_login_is_required(
        self,
        mock_generate_questions,
        mock_generate_diagnosis,
        mock_discover_centers,
    ):
        mock_generate_questions.return_value = [
            FollowUpQuestion(id=1, text="Any fever?", type="yesno", options=[]),
        ]
        mock_generate_diagnosis.return_value = TriageAssessment(
            conditions=[
                PossibleCondition(
                    name="General check",
                    likelihood="Moderate",
                    reasoning="Basic screening outcome.",
                    specialization="General Medicine",
                )
            ],
            urgency="Moderate",
            advice="Monitor and follow guidance.",
        )
        mock_discover_centers.return_value = []

        self.client.post(
            "/symptoms/question/",
            data={
                "age": 20,
                "gender": "Male",
                "state": "Mumbai, Maharashtra, India",
                "symptom": "headache",
            },
        )
        self.client.post("/symptoms/question/", data={"answer": "yes"})
        result_response = self.client.get("/symptoms/result/")
        self.assertEqual(result_response.status_code, 200)
        self.assertTrue(self.client.session.get("symptom_checker_guest_used_once"))

        second_attempt = self.client.post(
            "/symptoms/question/",
            data={
                "age": 20,
                "gender": "Male",
                "state": "Mumbai, Maharashtra, India",
                "symptom": "fever",
            },
            follow=True,
        )
        self.assertEqual(second_attempt.status_code, 200)
        self.assertContains(second_attempt, "Guest access allows one Symptom Checker run. Please login to continue.")
        self.assertContains(second_attempt, "Login Required")

    @patch("symptom_checker.engine.generate_questions")
    def test_logged_in_user_is_not_limited_by_guest_usage_flag(self, mock_generate_questions):
        mock_generate_questions.return_value = [
            FollowUpQuestion(id=1, text="Any fever?", type="yesno", options=[]),
        ]
        self.client.login(username="writer1", password="test-pass-123")
        session = self.client.session
        session["symptom_checker_guest_used_once"] = True
        session.save()

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
        self.assertContains(response, "Any fever?")

    @patch("symptom_checker.ai_client._generate_content_with_retry")
    def test_generate_symptom_suggestions_falls_back_when_ai_unavailable(self, mock_generate):
        mock_generate.side_effect = RuntimeError("quota")
        items = generate_symptom_suggestions("down", max_items=10)
        self.assertIn("Down syndrome", items)
        self.assertGreater(len(items), 0)

    @patch("symptom_checker.ai_client._generate_content_with_retry")
    def test_generate_symptom_suggestions_falls_back_when_ai_payload_invalid(self, mock_generate):
        mock_generate.return_value = '{"invalid":"payload"}'
        items = generate_symptom_suggestions("fev", max_items=10)
        self.assertIn("Fever", items)
        self.assertGreater(len(items), 0)

