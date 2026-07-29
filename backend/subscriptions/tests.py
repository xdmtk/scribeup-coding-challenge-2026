from datetime import datetime, timezone
from decimal import Decimal

from django.test import TestCase

from .merchant_groups import normalize_merchant
from .models import Transaction


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
