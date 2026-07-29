import io
import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from .models import Transaction
from .subscription_analysis import LIKELY_SUBSCRIPTION_THRESHOLD
from .subscription_audit import build_report, render_text, suspicious_reasons


class SubscriptionAuditCommandTests(TestCase):
    def add(self, user, merchant, date, amount="12.50"):
        Transaction.objects.create(user_id=user, merchant_name=merchant,
            amount=Decimal(amount), charged_at=datetime.fromisoformat(date).replace(tzinfo=timezone.utc))

    def setUp(self):
        for user in (1, 2):
            for day in ("2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15"):
                self.add(user, f"Monthly {user}", day)
            self.add(user, f"Irregular {user}", "2026-01-01", "10")
            self.add(user, f"Irregular {user}", "2026-01-03", "90")

    def run_command(self, **options):
        stdout = io.StringIO()
        call_command("audit_subscription_detection", stdout=stdout, **options)
        return stdout.getvalue()

    def test_default_includes_all_users_and_both_classifications(self):
        output = self.run_command()
        self.assertIn("USER 1", output)
        self.assertIn("USER 2", output)
        self.assertIn("LIKELY SUBSCRIPTIONS", output)
        self.assertIn("UNLIKELY SUBSCRIPTIONS", output)

    def test_user_option_limits_output(self):
        output = self.run_command(user=2)
        self.assertNotIn("USER 1\n", output)
        self.assertIn("USER 2", output)

    def test_json_is_valid_and_deterministic(self):
        first = self.run_command(format="json")
        self.assertEqual(first, self.run_command(format="json"))
        self.assertEqual([user["user_id"] for user in json.loads(first)["users"]], [1, 2])

    def test_output_file_and_parent_are_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "audit.json"
            message = self.run_command(format="json", output=str(path))
            self.assertIn("written to", message)
            self.assertEqual(json.loads(path.read_text())["summary"]["total_users"], 2)

    def test_invalid_reference_date_has_clear_error(self):
        with self.assertRaisesRegex(CommandError, "expected YYYY-MM-DD"):
            self.run_command(reference_date="tomorrow")

    def test_reuses_grouping_and_analysis_functions(self):
        with patch("subscriptions.management.commands.audit_subscription_detection.group_transactions") as grouping, \
             patch("subscriptions.management.commands.audit_subscription_detection.analyze_repeated_groups") as analysis:
            grouping.return_value = ([], [])
            analysis.return_value = {"likely_subscriptions": [], "unlikely_subscriptions": []}
            self.run_command()
            self.assertEqual(grouping.call_count, 2)
            self.assertEqual(analysis.call_count, 2)

    def test_currency_dates_and_transaction_order(self):
        output = self.run_command(user=1)
        self.assertIn("$12.50", output)
        self.assertLess(output.index("2026-04-15 | Monthly 1"), output.index("2026-01-15 | Monthly 1"))


class SubscriptionAuditReportingTests(TestCase):
    @staticmethod
    def item(confidence=.64, cadence="yearly", count=2, consistency=.6):
        return {"normalized_merchant": "example", "display_merchant": "Example",
            "merchant_variants": ["Example"], "transaction_count": count, "transactions": [],
            "classification": "likely" if confidence >= LIKELY_SUBSCRIPTION_THRESHOLD else "unlikely",
            "confidence_score": confidence,
            "detected_cadence": {"label": cadence, "typical_interval_days": 365,
                "intervals_days": [365], "consistency_score": consistency,
                "target_interval_days": 365, "tolerance_days": 15},
            "amount_analysis": {"typical_amount": "10.00", "min_amount": "10.00",
                "max_amount": "10.00", "relative_variation": 0, "consistency_score": 1},
            "activity": {"apparently_active": True, "days_since_last_charge": 0},
            "evidence": [{"type": "negative", "label": "No stable interval between charges"}]}

    def test_borderline_cases_are_closest_to_threshold_first(self):
        close, far = self.item(.679), self.item(.61)
        far["normalized_merchant"] = far["display_merchant"] = "Far"
        report = build_report([{"user_id": 1, "likely_subscriptions": [],
            "unlikely_subscriptions": [far, close]}], 4)
        self.assertEqual([item["display_merchant"] for item in report["borderline_cases"]], ["Example", "Far"])

    def test_cadence_evidence_conflict_is_flagged(self):
        self.assertIn("cadence label conflicts with evidence", suspicious_reasons(self.item()))

    def test_two_observation_high_confidence_is_flagged(self):
        self.assertIn("two observations with confidence >= 0.50", suspicious_reasons(self.item()))

    def test_text_group_format_is_stable(self):
        item = self.item()
        report = build_report([{"user_id": 4, "likely_subscriptions": [],
            "unlikely_subscriptions": [item]}], 2)
        output = render_text(report)
        self.assertIn("confidence: 0.640", output)
        self.assertIn("amount_range: $10.00–$10.00", output)
