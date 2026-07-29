from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from .merchant_groups import group_transactions, normalize_merchant
from .models import Transaction
from .subscription_analysis import analyze_merchant_group


class MerchantNormalizationTests(TestCase):
    def test_suffix_variants_normalize_together(self):
        keys = {normalize_merchant(name) for name in ("Netflix", "Netflix Inc", "NETFLIX.COM")}
        self.assertEqual(keys, {"netflix"})

    def test_case_and_whitespace_normalize_together(self):
        self.assertEqual(normalize_merchant("  ACME   Market  "), normalize_merchant("acme market"))

    def test_unrelated_names_remain_separate(self):
        self.assertNotEqual(normalize_merchant("Apple Store"), normalize_merchant("Applebee's"))


class MerchantGroupsEndpointTests(TestCase):
    @staticmethod
    def create_transaction(user_id, merchant, day, amount="10.00"):
        return Transaction.objects.create(
            user_id=user_id,
            merchant_name=merchant,
            amount=Decimal(amount),
            charged_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        )

    def test_groups_variants_and_requested_order(self):
        self.create_transaction(19, "Netflix", 1)
        self.create_transaction(19, "Netflix Inc", 3)
        self.create_transaction(19, "NETFLIX.COM", 2)
        self.create_transaction(19, "Alpha Corp", 4)
        self.create_transaction(19, "Alpha", 5)
        self.create_transaction(19, "Older Store", 6)
        self.create_transaction(19, "Newest Store", 7)

        response = self.client.get("/users/19/merchant-groups/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([g["normalized_merchant"] for g in data["repeated_merchants"]], ["netflix", "alpha"])
        netflix = data["repeated_merchants"][0]
        self.assertEqual(netflix["merchant_variants"], ["Netflix Inc", "NETFLIX.COM", "Netflix"])
        self.assertEqual([t["merchant_name"] for t in netflix["transactions"]], ["Netflix Inc", "NETFLIX.COM", "Netflix"])
        self.assertEqual([g["normalized_merchant"] for g in data["likely_one_off_merchants"]], ["newest store", "older store"])

    def test_repeated_and_one_off_classification(self):
        self.create_transaction(20, "Repeat", 1)
        self.create_transaction(20, "Repeat LLC", 2)
        self.create_transaction(20, "Single", 3)

        data = self.client.get("/users/20/merchant-groups/").json()

        self.assertEqual(data["repeated_merchants"][0]["transaction_count"], 2)
        self.assertEqual(data["likely_one_off_merchants"][0]["display_merchant"], "Single")

    def test_unknown_user_returns_not_found(self):
        response = self.client.get("/users/999/merchant-groups/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "User not found"})

    def test_analysis_only_contains_requested_users_transactions(self):
        self.create_transaction(19, "Shared Name", 1)
        self.create_transaction(19, "Shared Name", 8)
        self.create_transaction(20, "Shared Name", 15)

        data = self.client.get("/users/19/merchant-groups/").json()
        analysis = data["subscription_analysis"]
        analyzed = (analysis["likely_subscriptions"] + analysis["possible_subscriptions"] +
                    analysis["unlikely_subscriptions"])[0]

        self.assertEqual(analyzed["transaction_count"], 2)
        self.assertEqual({item["id"] for item in analyzed["transactions"]}, {1, 2})


class SubscriptionAnalysisTests(TestCase):
    reference_date = date(2026, 7, 15)

    @staticmethod
    def analyze(dates, amounts=None):
        amounts = amounts or ["15.99"] * len(dates)
        transactions = [
            SimpleNamespace(
                id=index,
                user_id=1,
                merchant_name="Example",
                amount=Decimal(amount),
                charged_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                raw_payload={},
            )
            for index, (day, amount) in enumerate(zip(dates, amounts), 1)
        ]
        repeated, _ = group_transactions(transactions)
        return analyze_merchant_group(repeated[0], SubscriptionAnalysisTests.reference_date)

    def test_stable_monthly_amount_is_likely(self):
        result = self.analyze([date(2026, month, 15) for month in range(2, 8)])
        self.assertEqual(result["classification"], "likely")
        self.assertEqual(result["detected_cadence"]["label"], "monthly")

    def test_quarterly_with_modest_amount_changes_is_likely(self):
        result = self.analyze(
            [date(2025, 4, 15), date(2025, 7, 15), date(2025, 10, 14),
             date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15)],
            ["170.70", "175.60", "182.27", "174.30", "180.10", "176.31"],
        )
        self.assertEqual(result["classification"], "likely")
        self.assertEqual(result["detected_cadence"]["label"], "quarterly")

    def test_irregular_variable_purchases_are_unlikely(self):
        result = self.analyze(
            [date(2026, 1, 1), date(2026, 1, 5), date(2026, 2, 20), date(2026, 6, 1), date(2026, 7, 15)],
            ["15.00", "220.00", "84.00", "13.00", "146.00"],
        )
        self.assertEqual(result["classification"], "unlikely")
        labels = [item["label"] for item in result["evidence"]]
        self.assertIn("Amounts vary substantially", labels)

    def test_timing_outweighs_amount_consistency(self):
        dates = [date(2026, month, 15) for month in range(2, 8)]
        stable_timing = self.analyze(dates, ["10", "18", "13", "20", "11", "17"])
        irregular_timing = self.analyze(
            [date(2026, 1, 1), date(2026, 1, 10), date(2026, 3, 20), date(2026, 7, 15)],
            ["15"] * 4,
        )
        self.assertGreater(stable_timing["confidence_score"], irregular_timing["confidence_score"])

    def test_two_identical_monthly_transactions_are_possible_but_not_likely(self):
        result = self.analyze([date(2026, 6, 15), date(2026, 7, 15)])
        self.assertEqual(result["classification"], "possible")
        self.assertLessEqual(result["confidence_score"], 0.64)

    def test_more_observations_increase_confidence(self):
        few = self.analyze([date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 15)])
        many = self.analyze([date(2026, month, 15) for month in range(2, 8)])
        self.assertGreater(many["confidence_score"], few["confidence_score"])

    def test_skipped_month_still_supports_monthly(self):
        result = self.analyze([
            date(2026, 2, 15), date(2026, 3, 15), date(2026, 5, 15),
            date(2026, 6, 15), date(2026, 7, 15),
        ])
        self.assertEqual(result["detected_cadence"]["label"], "monthly")
        self.assertEqual(result["classification"], "likely")

    def test_four_weeks_is_distinct_from_calendar_monthly(self):
        four_weeks = self.analyze([
            date(2026, 4, 22), date(2026, 5, 20), date(2026, 6, 17), date(2026, 7, 15),
        ])
        monthly = self.analyze([
            date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 15),
        ])
        self.assertEqual(four_weeks["detected_cadence"]["label"], "every four weeks")
        self.assertEqual(monthly["detected_cadence"]["label"], "monthly")

    def test_inactive_pattern_has_lower_confidence_and_evidence(self):
        old = self.analyze([date(2024, month, 15) for month in range(1, 7)])
        current = self.analyze([date(2026, month, 15) for month in range(2, 8)])
        self.assertLess(old["confidence_score"], current["confidence_score"])
        self.assertFalse(old["activity"]["apparently_active"])
        self.assertIn("Pattern appears inactive", [item["label"] for item in old["evidence"]])

    def test_evidence_and_score_are_explainable_and_bounded(self):
        for result in (
            self.analyze([date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 15)]),
            self.analyze([date(2026, 1, 1), date(2026, 2, 20)], ["1", "100"]),
        ):
            self.assertGreaterEqual(result["confidence_score"], 0.0)
            self.assertLessEqual(result["confidence_score"], 1.0)
            self.assertTrue(result["evidence"])
            self.assertTrue({item["type"] for item in result["evidence"]}.issubset({"positive", "negative"}))

    def test_noisy_monthly_history_with_one_skip_is_likely(self):
        gaps = [32, 28, 32, 34, 25, 31, 34, 29, 55, 32, 27, 32, 34, 30, 28, 32]
        dates = [date(2025, 1, 1)]
        for gap in gaps:
            dates.append(dates[-1] + timedelta(days=gap))
        result = self.analyze(dates)
        cadence = result["detected_cadence"]
        self.assertEqual(result["classification"], "likely")
        self.assertEqual(cadence["label"], "monthly")
        self.assertGreaterEqual(cadence["direct_match_ratio"], .85)
        self.assertEqual(cadence["skipped_match_count"], 1)
        self.assertEqual(result["amount_analysis"]["consistency_score"], 1)

    def test_three_long_intervals_do_not_invent_custom_cadence(self):
        result = self.analyze(
            [date(2024, 1, 1), date(2024, 8, 26), date(2025, 4, 22)],
            ["517.67", "907.55", "1320.12"],
        )
        self.assertIsNone(result["detected_cadence"]["label"])
        self.assertEqual(result["classification"], "unlikely")
        self.assertLess(result["amount_analysis"]["consistency_score"], .35)
        self.assertIn("Insufficient history to establish a custom cadence",
                      [item["label"] for item in result["evidence"]])

    def test_skips_without_direct_support_do_not_become_monthly(self):
        start = date(2025, 1, 1)
        dates = [start + timedelta(days=60 * index) for index in range(5)]
        self.assertNotEqual(self.analyze(dates)["detected_cadence"]["label"], "monthly")

    def test_custom_cadence_requires_five_transactions(self):
        start = date(2025, 1, 1)
        four = self.analyze([start + timedelta(days=40 * index) for index in range(4)])
        five = self.analyze([start + timedelta(days=40 * index) for index in range(5)])
        self.assertIsNone(four["detected_cadence"]["label"])
        self.assertEqual(five["detected_cadence"]["label"], "every_40_days")

    def test_equal_amounts_alone_cannot_be_likely_or_active(self):
        result = self.analyze([date(2025, 1, 1), date(2025, 1, 10), date(2025, 4, 1),
                               date(2025, 8, 20), date(2026, 7, 15)])
        self.assertEqual(result["amount_analysis"]["consistency_score"], 1)
        self.assertEqual(result["classification"], "unlikely")
        self.assertIsNone(result["activity"]["apparently_active"])

    def test_cadence_label_never_has_no_stable_interval_evidence(self):
        result = self.analyze([date(2026, month, 15) for month in range(2, 8)])
        labels = [item["label"] for item in result["evidence"]]
        self.assertNotIn("No stable interval between charges", labels)

    def test_two_identical_yearly_charges_are_possible(self):
        result = self.analyze([date(2025, 7, 15), date(2026, 7, 15)], ["100", "100"])
        self.assertEqual(result["classification"], "possible")
        self.assertEqual(result["detected_cadence"]["label"], "yearly")
        self.assertIn("More history is needed to confirm recurrence",
                      [item["label"] for item in result["evidence"]])
        self.assertFalse(any("Stable" in item["label"] for item in result["evidence"]))

    def test_two_variable_yearly_purchases_are_unlikely(self):
        result = self.analyze([date(2025, 7, 15), date(2026, 7, 15)], ["100", "125"])
        self.assertEqual(result["classification"], "unlikely")

    def test_two_identical_charges_without_named_cadence_are_unlikely(self):
        result = self.analyze([date(2026, 6, 5), date(2026, 7, 15)])
        self.assertEqual(result["classification"], "unlikely")
        self.assertIsNone(result["detected_cadence"]["label"])

    def test_two_charges_supported_only_as_skip_are_unlikely(self):
        # A 52-day interval can be explained as two monthly cycles, but has no
        # direct cadence support and therefore cannot be possible.
        result = self.analyze([date(2026, 5, 24), date(2026, 7, 15)])
        self.assertEqual(result["classification"], "unlikely")

    def test_three_loose_semiannual_charges_are_possible(self):
        result = self.analyze([date(2025, 7, 10), date(2026, 1, 19), date(2026, 7, 15)])
        self.assertEqual(result["detected_cadence"]["label"], "semiannual")
        self.assertEqual(result["classification"], "possible")

    def test_three_variable_semiannual_charges_are_unlikely(self):
        result = self.analyze(
            [date(2025, 7, 10), date(2026, 1, 19), date(2026, 7, 15)],
            ["109", "145", "82"],
        )
        self.assertEqual(result["classification"], "unlikely")

    def test_sparse_evidence_strength_increases_with_an_observation(self):
        two = self.analyze([date(2025, 7, 15), date(2026, 7, 15)])
        three = self.analyze([date(2025, 7, 10), date(2026, 1, 19), date(2026, 7, 15)])
        long = self.analyze([date(2026, month, 15) for month in range(2, 8)])
        self.assertLess(two["evidence_strength_score"], three["evidence_strength_score"])
        self.assertLess(three["evidence_strength_score"], long["evidence_strength_score"])
        for result in (two, three, long):
            self.assertGreaterEqual(result["pattern_quality_score"], 0)
            self.assertLessEqual(result["pattern_quality_score"], 1)
            self.assertGreaterEqual(result["evidence_strength_score"], 0)
            self.assertLessEqual(result["evidence_strength_score"], 1)
