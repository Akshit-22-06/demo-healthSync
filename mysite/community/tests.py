from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from community.models import CommunityAccessTag, CommunityMessage, CommunityRoom
from community.services import (
    CATEGORY_GENERAL,
    CATEGORY_MIND,
    CATEGORY_SENIOR,
    CATEGORY_SKIN,
    ROOM_CODE_GENERAL,
    ROOM_CODE_MIND,
    ROOM_CODE_SENIOR,
    ROOM_CODE_SKIN,
    evaluate_chat_access_eligibility,
    sync_default_community_rooms,
)


class CommunityAccessFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="community-user",
            email="community@example.com",
            password="test-pass-123",
        )
        self.client.login(username="community-user", password="test-pass-123")
        sync_default_community_rooms()

    def test_locked_without_symptom_snapshot_or_tag(self):
        response = self.client.get(reverse("community"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete a Symptom Checker session to determine eligibility")

    def test_serious_match_grants_access_tag(self):
        diagnosis = {
            "urgency": "High",
            "conditions": [{"name": "Down syndrome support need", "likelihood": "High"}],
        }
        intake = {"symptom": "down syndrome", "age": 20}

        first = evaluate_chat_access_eligibility(user=self.user, intake=intake, diagnosis=diagnosis)
        self.assertEqual(first["status"], "approved")
        self.assertEqual(first["category"], CATEGORY_MIND)
        self.assertIn(ROOM_CODE_MIND, first["community_url"])
        self.assertTrue(
            CommunityAccessTag.objects.filter(
                user=self.user,
                status=CommunityAccessTag.Status.APPROVED,
                category=CATEGORY_MIND,
            ).exists()
        )

    def test_unmapped_case_routes_to_general_group(self):
        diagnosis = {
            "urgency": "High",
            "conditions": [{"name": "Nonspecific condition", "likelihood": "High"}],
        }
        intake = {"symptom": "unmapped symptom text"}

        outcome = evaluate_chat_access_eligibility(user=self.user, intake=intake, diagnosis=diagnosis)
        self.assertEqual(outcome["status"], "approved")
        self.assertEqual(outcome["category"], CATEGORY_GENERAL)
        self.assertIn(ROOM_CODE_GENERAL, outcome["community_url"])

    def test_skin_case_routes_to_skin_group(self):
        diagnosis = {
            "urgency": "High",
            "conditions": [{"name": "Fungal Skin Infection", "likelihood": "High"}],
        }
        intake = {"symptom": "skin rash and itching", "age": 28}

        outcome = evaluate_chat_access_eligibility(user=self.user, intake=intake, diagnosis=diagnosis)
        self.assertEqual(outcome["status"], "approved")
        self.assertEqual(outcome["category"], CATEGORY_SKIN)
        self.assertIn(ROOM_CODE_SKIN, outcome["community_url"])

    def test_senior_case_routes_to_senior_group(self):
        diagnosis = {
            "urgency": "High",
            "conditions": [{"name": "General frailty", "likelihood": "High"}],
        }
        intake = {"symptom": "fatigue while walking", "age": 68}

        outcome = evaluate_chat_access_eligibility(user=self.user, intake=intake, diagnosis=diagnosis)
        self.assertEqual(outcome["status"], "approved")
        self.assertEqual(outcome["category"], CATEGORY_SENIOR)
        self.assertIn(ROOM_CODE_SENIOR, outcome["community_url"])

    def test_request_access_when_already_approved(self):
        tag = CommunityAccessTag.objects.create(
            user=self.user,
            tag_code="MIND_SEVERE",
            category=CATEGORY_MIND,
            risk_level="SERIOUS",
            confidence_score=0.82,
            recurrence_count=2,
            status=CommunityAccessTag.Status.APPROVED,
        )

        response = self.client.post(reverse("community_request_access"), follow=True)
        self.assertEqual(response.status_code, 200)

        tag.refresh_from_db()
        self.assertEqual(tag.status, CommunityAccessTag.Status.APPROVED)

    def test_room_access_requires_approved_chat_tag(self):
        support_room = CommunityRoom.objects.get(code=ROOM_CODE_MIND)
        blocked = self.client.get(reverse("community_room", kwargs={"room_code": support_room.code}))
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.url, reverse("community"))

        CommunityAccessTag.objects.create(
            user=self.user,
            tag_code="MIND_CHRONIC",
            category=CATEGORY_MIND,
            risk_level="SERIOUS",
            confidence_score=0.88,
            recurrence_count=4,
            status=CommunityAccessTag.Status.APPROVED,
        )
        allowed = self.client.get(reverse("community_room", kwargs={"room_code": support_room.code}))
        self.assertEqual(allowed.status_code, 200)
        self.assertContains(allowed, support_room.name)

    def test_non_chat_room_is_blocked_even_with_chat_tag(self):
        room = CommunityRoom.objects.create(
            code="resp-room-temp",
            category="RESP",
            name="Resp Community",
            description="temp",
            is_active=True,
        )
        CommunityAccessTag.objects.create(
            user=self.user,
            tag_code="MIND_CHRONIC",
            category=CATEGORY_MIND,
            risk_level="SERIOUS",
            confidence_score=0.88,
            recurrence_count=4,
            status=CommunityAccessTag.Status.APPROVED,
        )
        blocked = self.client.get(reverse("community_room", kwargs={"room_code": room.code}))
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.url, reverse("community"))

    def test_unsafe_message_is_blocked(self):
        room = CommunityRoom.objects.get(code=ROOM_CODE_MIND)
        CommunityAccessTag.objects.create(
            user=self.user,
            tag_code="MIND_SEVERE",
            category=CATEGORY_MIND,
            risk_level="SERIOUS",
            confidence_score=0.8,
            recurrence_count=2,
            status=CommunityAccessTag.Status.APPROVED,
        )

        response = self.client.post(
            reverse("community_room", kwargs={"room_code": room.code}),
            data={"message": "You should stop your medicine and ignore doctor advice."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        blocked = CommunityMessage.objects.get(room=room, user=self.user)
        self.assertTrue(blocked.is_blocked)
        self.assertTrue(blocked.is_flagged)
        self.assertContains(response, "Unsafe advice detected")

    def test_unlocked_banner_is_shown_once(self):
        CommunityAccessTag.objects.create(
            user=self.user,
            tag_code="MIND_SEVERE",
            category=CATEGORY_MIND,
            risk_level="SERIOUS",
            confidence_score=0.85,
            recurrence_count=2,
            status=CommunityAccessTag.Status.APPROVED,
        )

        first = self.client.get(reverse("community"))
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, "Community Chat Unlocked")

        second = self.client.get(reverse("community"))
        self.assertEqual(second.status_code, 200)
        self.assertNotContains(second, "Community Chat Unlocked")
