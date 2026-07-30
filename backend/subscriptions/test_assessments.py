from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings

from .assessments import get_or_refresh_user_assessments, transaction_fingerprint
from .models import SubscriptionAssessment, Transaction
from .prediction import predict_next_charge


class FingerprintTests(TestCase):
    def setUp(self):
        self.first = Transaction.objects.create(user_id=7, merchant_name="Example", amount="10.00",
            charged_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
        self.second = Transaction.objects.create(user_id=7, merchant_name="Example", amount="10.00",
            charged_at=datetime(2026, 2, 1, 12, tzinfo=timezone.utc))

    def fingerprint(self, items):
        return transaction_fingerprint(7, "example", items)

    def test_order_is_stable_and_changes_are_detected(self):
        original = self.fingerprint([self.first, self.second])
        self.assertEqual(original, self.fingerprint([self.second, self.first]))
        self.second.amount = Decimal("11.00")
        self.assertNotEqual(original, self.fingerprint([self.first, self.second]))
        self.second.refresh_from_db()
        self.second.charged_at = datetime(2026, 2, 2, 12, tzinfo=timezone.utc)
        self.assertNotEqual(original, self.fingerprint([self.first, self.second]))
        self.assertNotEqual(original, self.fingerprint([self.first]))


class PredictionTests(TestCase):
    def test_calendar_and_fixed_cadences(self):
        self.assertEqual(predict_next_charge(date(2025, 1, 31), "monthly", date(2025, 1, 31)),
                         date(2025, 2, 28))
        self.assertEqual(predict_next_charge(date(2024, 2, 29), "yearly", date(2024, 3, 1)),
                         date(2025, 2, 28))
        self.assertEqual(predict_next_charge(date(2025, 1, 31), "quarterly", date(2025, 2, 1)),
                         date(2025, 4, 30))
        self.assertEqual(predict_next_charge(date(2025, 1, 1), "every_40_days", date(2025, 4, 1)),
                         date(2025, 5, 1))


@override_settings(OPENAI_SUBSCRIPTION_REVIEW_ENABLED=False)
class AssessmentPersistenceTests(TestCase):
    def add(self, merchant, day, amount="12.00"):
        return Transaction.objects.create(user_id=31, merchant_name=merchant, amount=amount,
            charged_at=datetime(2026, day, 15, tzinfo=timezone.utc))

    def setUp(self):
        for month in range(1, 7):
            self.add("Monthly Service", month)

    def test_create_reuse_endpoint_and_selective_refresh(self):
        first = get_or_refresh_user_assessments(31)
        self.assertEqual(first.stats.stale_assessments_refreshed, 1)
        self.assertEqual(SubscriptionAssessment.objects.count(), 1)
        updated_at = first.assessments[0].updated_at
        with patch("subscriptions.assessments.review_subscription_candidate") as review:
            second = get_or_refresh_user_assessments(31)
        review.assert_not_called()
        self.assertEqual(second.stats.cached_assessments_reused, 1)
        self.assertEqual(second.assessments[0].updated_at, updated_at)
        response = self.client.get("/users/31/subscriptions/")
        item = response.json()["subscriptions"][0]
        self.assertEqual(set(("merchant", "cadence", "typical_amount",
                              "next_predicted_charge_date")) - set(item), set())
        self.assertEqual(item["typical_amount"], "12.00")

    def test_removed_group_is_deleted_and_unknown_user_is_404(self):
        get_or_refresh_user_assessments(31)
        Transaction.objects.filter(user_id=31).exclude(
            pk=Transaction.objects.filter(user_id=31).values_list("pk", flat=True).first()
        ).delete()
        get_or_refresh_user_assessments(31)
        self.assertFalse(SubscriptionAssessment.objects.exists())
        self.assertEqual(self.client.get("/users/999/subscriptions/").status_code, 404)

    def test_unique_constraint(self):
        get_or_refresh_user_assessments(31)
        row = SubscriptionAssessment.objects.get()
        row.pk = None
        with self.assertRaises(IntegrityError):
            row.save()


@override_settings(OPENAI_SUBSCRIPTION_REVIEW_ENABLED=True, OPENAI_API_KEY="fake-test-key")
class LlmRoutingTests(TestCase):
    def setUp(self):
        for month in (1, 2):
            Transaction.objects.create(user_id=40, merchant_name="Candidate", amount="10.00",
                charged_at=datetime(2026, month, 15, tzinfo=timezone.utc))

    def test_possible_calls_once_then_reuses(self):
        review_result = type("Review", (), {"classification": "subscription", "confidence": .9,
            "reason": "Recurring service.", "as_dict": lambda self: {
                "classification": "subscription", "confidence": .9,
                "merchant_type": "recurring_service", "reason": "Recurring service."}})()
        with patch("subscriptions.assessments.review_subscription_candidate", return_value=review_result) as review:
            get_or_refresh_user_assessments(40)
            get_or_refresh_user_assessments(40)
        self.assertEqual(review.call_count, 1)
        self.assertEqual(SubscriptionAssessment.objects.get().llm_review_status, "completed")

    @override_settings(OPENAI_SUBSCRIPTION_REVIEW_ENABLED=False)
    def test_disabled_possible_is_uncertain(self):
        with patch("subscriptions.assessments.review_subscription_candidate") as review:
            get_or_refresh_user_assessments(40)
        review.assert_not_called()
        row = SubscriptionAssessment.objects.get()
        self.assertEqual((row.final_classification, row.llm_review_status), ("uncertain", "disabled"))

    def test_failure_is_safe_uncertain(self):
        with patch("subscriptions.assessments.review_subscription_candidate", side_effect=TimeoutError):
            get_or_refresh_user_assessments(40)
        row = SubscriptionAssessment.objects.get()
        self.assertEqual((row.final_classification, row.llm_review_status), ("uncertain", "failed"))
