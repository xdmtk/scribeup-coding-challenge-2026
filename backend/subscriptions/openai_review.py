"""Narrow, backend-only semantic review using the OpenAI Responses API."""

import json
import importlib
from dataclasses import dataclass

from django.conf import settings


CLASSIFICATIONS = {"subscription", "not_subscription", "uncertain"}
MERCHANT_TYPES = {"software_subscription", "media_subscription", "membership", "insurance",
                  "utility", "recurring_service", "repeat_retail_purchase",
                  "discretionary_purchase", "unknown"}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "classification": {"type": "string", "enum": sorted(CLASSIFICATIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "merchant_type": {"type": "string", "enum": sorted(MERCHANT_TYPES)},
        "reason": {"type": "string"},
    },
    "required": ["classification", "confidence", "merchant_type", "reason"],
}
INSTRUCTIONS = """Judge whether this merchant pattern is a subscription, membership, or automatically
recurring service; a repeat/discretionary retail purchase; or uncertain. Transaction evidence is
primary and general merchant context is secondary. Repeated purchasing alone is not a subscription.
Memberships and automatic recurrence count; repeat retail purchases do not. Use uncertain when
evidence is insufficient. Do not invent transaction facts. Return only schema-compliant output."""


@dataclass(frozen=True)
class SubscriptionReviewResult:
    classification: str
    confidence: float
    merchant_type: str
    reason: str

    def as_dict(self):
        return {"classification": self.classification, "confidence": self.confidence,
                "merchant_type": self.merchant_type, "reason": self.reason}


def build_review_input(group, result):
    cadence = result["detected_cadence"]
    amounts = result["amount_analysis"]
    return {
        "merchant": group["display_merchant"],
        "merchant_variants": group["merchant_variants"],
        "heuristic_classification": result["classification"],
        "transaction_count": group["transaction_count"],
        "dates": [item["charged_at"][:10] for item in group["transactions"]],
        "amounts": [item["amount"] for item in group["transactions"]],
        "cadence": cadence["label"], "intervals_days": cadence["intervals_days"],
        "timing_consistency": cadence["consistency_score"],
        "direct_match_ratio": cadence["direct_match_ratio"],
        "amount_consistency": amounts["consistency_score"],
        "pattern_quality": result["pattern_quality_score"],
        "evidence_strength": result["evidence_strength_score"],
        "heuristic_evidence": [item["label"] for item in result["evidence"]],
    }


def _validate(payload):
    if not isinstance(payload, dict) or set(payload) != set(SCHEMA["required"]):
        raise ValueError("OpenAI returned an invalid structured result")
    if payload["classification"] not in CLASSIFICATIONS or payload["merchant_type"] not in MERCHANT_TYPES:
        raise ValueError("OpenAI returned an unsupported classification")
    confidence = float(payload["confidence"])
    if not 0 <= confidence <= 1 or not isinstance(payload["reason"], str) or not payload["reason"].strip():
        raise ValueError("OpenAI returned invalid confidence or reason")
    return SubscriptionReviewResult(payload["classification"], confidence,
                                    payload["merchant_type"], payload["reason"].strip())


def review_subscription_candidate(group, heuristic_result):
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    client = importlib.import_module("openai").OpenAI(
        api_key=settings.OPENAI_API_KEY, timeout=settings.OPENAI_TIMEOUT_SECONDS)
    response = client.responses.create(
        model=settings.OPENAI_MODEL, store=False,
        instructions=INSTRUCTIONS,
        input=json.dumps(build_review_input(group, heuristic_result), sort_keys=True),
        text={"format": {"type": "json_schema", "name": "subscription_review",
                         "strict": True, "schema": SCHEMA}},
    )
    return _validate(json.loads(response.output_text))
