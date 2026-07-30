import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from .finalization import offline_decision, requires_llm_review
from .merchant_groups import group_transactions
from .models import SubscriptionAssessment, Transaction
from .openai_review import review_subscription_candidate
from .prediction import predict_next_charge
from .subscription_analysis import analyze_merchant_group
from .versions import FINALIZATION_VERSION, HEURISTIC_VERSION, LLM_PROMPT_VERSION


def transaction_fingerprint(user_id, normalized_merchant, transactions):
    payload = {
        "user_id": user_id,
        "normalized_merchant": normalized_merchant,
        "transactions": sorted(({
            "id": item.id,
            "merchant_name": item.merchant_name,
            "charged_at": item.charged_at.isoformat(),
            "amount": str(item.amount),
        } for item in transactions), key=lambda item: (item["charged_at"], item["id"])),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class RefreshStats:
    merchant_groups_processed: int = 0
    cached_assessments_reused: int = 0
    stale_assessments_refreshed: int = 0
    heuristic_only_finalizations: int = 0
    llm_reviews_attempted: int = 0
    llm_reviews_completed: int = 0
    llm_reviews_failed: int = 0


@dataclass
class AssessmentResult:
    assessments: list
    stats: RefreshStats


def _valid(existing, fingerprint, review_required, llm_enabled):
    if not existing or existing.input_fingerprint != fingerprint:
        return False
    if (existing.heuristic_version != HEURISTIC_VERSION or
            existing.finalization_version != FINALIZATION_VERSION):
        return False
    if review_required:
        if (existing.llm_prompt_version != LLM_PROMPT_VERSION or
                existing.llm_model != settings.OPENAI_MODEL):
            return False
        if llm_enabled and existing.llm_review_status != "completed":
            return False
    return True


def _defaults(user_id, group, heuristic, fingerprint, reference_date, allow_llm, stats):
    review_required = requires_llm_review(heuristic)
    final, confidence, reason = offline_decision(heuristic)
    source, status, llm_payload, error = "heuristic", "not_required", None, ""
    llm_enabled = bool(allow_llm and settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED)
    if review_required:
        source = "heuristic_fallback"
        if not llm_enabled:
            status = "disabled"
            reason = "Semantic review is disabled; ambiguous result remains uncertain."
        else:
            stats.llm_reviews_attempted += 1
            try:
                review = review_subscription_candidate(group, heuristic)
                llm_payload = review.as_dict()
                final, confidence, reason = review.classification, review.confidence, review.reason
                source, status = "llm_review", "completed"
                stats.llm_reviews_completed += 1
            except Exception as exc:  # API, timeout, rate-limit, and validation failures are safe.
                status = "failed"
                error = f"{type(exc).__name__}: semantic review unavailable"
                reason = "Semantic review failed; ambiguous result remains uncertain."
                stats.llm_reviews_failed += 1
    else:
        stats.heuristic_only_finalizations += 1

    cadence = heuristic["detected_cadence"]["label"] or ""
    latest = max(item.charged_at.date() for item in group["_transaction_objects"])
    next_date = predict_next_charge(latest, cadence, reference_date) if final == "subscription" else None
    return {
        "display_merchant": group["display_merchant"], "input_fingerprint": fingerprint,
        "heuristic_version": HEURISTIC_VERSION, "finalization_version": FINALIZATION_VERSION,
        "llm_prompt_version": LLM_PROMPT_VERSION if review_required else "",
        "llm_model": settings.OPENAI_MODEL if review_required else "",
        "heuristic_classification": heuristic["classification"],
        "heuristic_payload": heuristic, "llm_review_required": review_required,
        "llm_review_status": status, "llm_payload": llm_payload, "llm_error": error,
        "final_classification": final, "final_confidence": confidence, "final_reason": reason,
        "cadence": cadence, "typical_amount": Decimal(heuristic["amount_analysis"]["typical_amount"]),
        "next_predicted_charge_date": next_date, "assessment_source": source,
    }


def get_or_refresh_user_assessments(user_id, *, allow_llm=True, force=False):
    txns = list(Transaction.objects.filter(user_id=user_id).order_by("charged_at", "id"))
    if not txns:
        return None
    groups, _ = group_transactions(txns)
    existing = {row.normalized_merchant: row for row in
                SubscriptionAssessment.objects.filter(user_id=user_id)}
    stats = RefreshStats(merchant_groups_processed=len(groups))
    reference_date = max(item.charged_at.date() for item in txns)
    results = []
    active_keys = {group["normalized_merchant"] for group in groups}
    for group in groups:
        key = group["normalized_merchant"]
        fingerprint = transaction_fingerprint(user_id, key, group["_transaction_objects"])
        # The routing decision is deterministic, so analyze before deciding cache validity.
        heuristic = analyze_merchant_group(group, reference_date)
        required = requires_llm_review(heuristic)
        llm_enabled = bool(allow_llm and settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED)
        if not force and _valid(existing.get(key), fingerprint, required, llm_enabled):
            results.append(existing[key])
            stats.cached_assessments_reused += 1
            continue
        defaults = _defaults(user_id, group, heuristic, fingerprint, reference_date, allow_llm, stats)
        try:
            with transaction.atomic():
                row, _ = SubscriptionAssessment.objects.update_or_create(
                    user_id=user_id, normalized_merchant=key, defaults=defaults)
        except IntegrityError:
            row = SubscriptionAssessment.objects.get(user_id=user_id, normalized_merchant=key)
        results.append(row)
        stats.stale_assessments_refreshed += 1
    SubscriptionAssessment.objects.filter(user_id=user_id).exclude(
        normalized_merchant__in=active_keys).delete()
    results.sort(key=lambda item: item.normalized_merchant)
    return AssessmentResult(results, stats)
