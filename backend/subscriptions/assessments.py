import hashlib
import json
import logging
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

logger = logging.getLogger("subscriptions.semantic_review")
_config_logged = False


def _boolean(value):
    return str(bool(value)).lower()


def log_review_configuration():
    """Log safe semantic-review configuration once per process."""
    global _config_logged
    if _config_logged:
        return
    _config_logged = True
    logger.info(
        "[SubscriptionReview][Config] enabled=%s api_key_configured=%s model=%s "
        "timeout_seconds=%s loaded_env_paths=%s",
        _boolean(settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED),
        _boolean(settings.OPENAI_API_KEY), settings.OPENAI_MODEL,
        settings.OPENAI_TIMEOUT_SECONDS, settings.LOADED_ENV_PATH or "none")


def transaction_fingerprint(user_id, normalized_merchant, transactions):
    payload = {
        "user_id": user_id, "normalized_merchant": normalized_merchant,
        "transactions": sorted(({"id": item.id, "merchant_name": item.merchant_name,
            "charged_at": item.charged_at.isoformat(), "amount": str(item.amount)}
            for item in transactions), key=lambda item: (item["charged_at"], item["id"])),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class CacheValidation:
    valid: bool
    reason: str


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


def validate_cached_assessment(existing, fingerprint, review_required, llm_enabled, *, force=False):
    """Return the first deterministic reason that a snapshot is valid or stale."""
    if force:
        return CacheValidation(False, "force_refresh")
    if not existing:
        return CacheValidation(False, "no_existing_assessment")
    if existing.input_fingerprint != fingerprint:
        return CacheValidation(False, "fingerprint_changed")
    if existing.heuristic_version != HEURISTIC_VERSION:
        return CacheValidation(False, "heuristic_version_changed")
    if existing.finalization_version != FINALIZATION_VERSION:
        return CacheValidation(False, "finalization_version_changed")
    if review_required:
        if existing.llm_prompt_version != LLM_PROMPT_VERSION:
            return CacheValidation(False, "prompt_version_changed")
        if existing.llm_model != settings.OPENAI_MODEL:
            return CacheValidation(False, "model_changed")
        if llm_enabled and existing.llm_review_status != "completed":
            return CacheValidation(False, "llm_review_not_completed")
    return CacheValidation(True, "valid")


def _route_log(user_id, group, heuristic, required, allow_llm, action):
    logger.info(
        "[SubscriptionReview][Route] user_id=%s merchant=%s heuristic_classification=%s "
        "review_required=%s allow_llm=%s review_enabled=%s api_key_configured=%s action=%s",
        user_id, group["normalized_merchant"], heuristic["classification"],
        _boolean(required), _boolean(allow_llm),
        _boolean(settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED),
        _boolean(settings.OPENAI_API_KEY), action)


def _defaults(user_id, group, heuristic, fingerprint, reference_date, allow_llm, stats):
    required = requires_llm_review(heuristic)
    final, confidence, reason = offline_decision(heuristic)
    source, status, llm_payload, error = "heuristic", "not_required", None, ""
    enabled = bool(allow_llm and settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED)
    if not required:
        action = "finalize_offline"
        stats.heuristic_only_finalizations += 1
    elif not allow_llm or not settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED:
        action, source, status = "fallback_disabled", "heuristic_fallback", "disabled"
        reason = "Semantic review is disabled; ambiguous result remains uncertain."
    elif not settings.OPENAI_API_KEY:
        action, source, status = "fallback_missing_key", "heuristic_fallback", "misconfigured"
        reason = "Semantic review is enabled but not configured; ambiguous result remains uncertain."
        error = "MissingOpenAIAPIKey: semantic review is not configured"
    else:
        action, source = "call_openai", "heuristic_fallback"
    _route_log(user_id, group, heuristic, required, allow_llm, action)

    if action == "call_openai":
        stats.llm_reviews_attempted += 1
        try:
            review = review_subscription_candidate(group, heuristic, user_id=user_id)
            llm_payload = review.as_dict()
            final, confidence, reason = review.classification, review.confidence, review.reason
            source, status = "llm_review", "completed"
            stats.llm_reviews_completed += 1
        except Exception as exc:  # SDK, timeout, rate-limit and validation failures are safe.
            status = "failed"
            error = f"{type(exc).__name__}: semantic review unavailable"
            reason = "Semantic review failed; ambiguous result remains uncertain."
            stats.llm_reviews_failed += 1
            logger.warning("[SubscriptionReview][Failure] user_id=%s merchant=%s error_type=%s",
                           user_id, group["normalized_merchant"], type(exc).__name__)
            logger.debug("Semantic review failure details", exc_info=True)

    cadence = heuristic["detected_cadence"]["label"] or ""
    latest = max(item.charged_at.date() for item in group["_transaction_objects"])
    next_date = predict_next_charge(latest, cadence, reference_date) if final == "subscription" else None
    return {
        "display_merchant": group["display_merchant"], "input_fingerprint": fingerprint,
        "heuristic_version": HEURISTIC_VERSION, "finalization_version": FINALIZATION_VERSION,
        "llm_prompt_version": LLM_PROMPT_VERSION if required else "",
        "llm_model": settings.OPENAI_MODEL if required else "",
        "heuristic_classification": heuristic["classification"], "heuristic_payload": heuristic,
        "llm_review_required": required, "llm_review_status": status,
        "llm_payload": llm_payload, "llm_error": error, "final_classification": final,
        "final_confidence": confidence, "final_reason": reason, "cadence": cadence,
        "typical_amount": Decimal(heuristic["amount_analysis"]["typical_amount"]),
        "next_predicted_charge_date": next_date, "assessment_source": source,
    }


def get_or_refresh_user_assessments(user_id, *, allow_llm=True, force=False,
                                    merchant_keys=None):
    log_review_configuration()
    txns = list(Transaction.objects.filter(user_id=user_id).order_by("charged_at", "id"))
    if not txns:
        return None
    groups, _ = group_transactions(txns)
    if merchant_keys is not None:
        groups = [group for group in groups if group["normalized_merchant"] in merchant_keys]
    existing = {row.normalized_merchant: row for row in
                SubscriptionAssessment.objects.filter(user_id=user_id)}
    stats = RefreshStats(merchant_groups_processed=len(groups))
    reference_date = max(item.charged_at.date() for item in txns)
    results = []
    logger.info("[SubscriptionAssessment][Start] user_id=%s allow_llm=%s review_enabled=%s "
                "force=%s merchant_groups=%s", user_id, _boolean(allow_llm),
                _boolean(settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED), _boolean(force), len(groups))
    for group in groups:
        key = group["normalized_merchant"]
        fingerprint = transaction_fingerprint(user_id, key, group["_transaction_objects"])
        heuristic = analyze_merchant_group(group, reference_date)
        required = requires_llm_review(heuristic)
        llm_enabled = bool(allow_llm and settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED)
        cached = existing.get(key)
        logger.info("[SubscriptionAssessment][Merchant] user_id=%s merchant=%s "
                    "heuristic_classification=%s review_required=%s cached_row_exists=%s",
                    user_id, key, heuristic["classification"], _boolean(required), _boolean(cached))
        validation = validate_cached_assessment(cached, fingerprint, required, llm_enabled,
                                                force=force)
        if validation.valid:
            logger.info("[SubscriptionAssessment][CacheHit] user_id=%s merchant=%s "
                        "final_classification=%s llm_status=%s assessment_source=%s",
                        user_id, key, cached.final_classification, cached.llm_review_status,
                        cached.assessment_source)
            _route_log(user_id, group, heuristic, required, allow_llm,
                       "reuse_cached_review" if required else "finalize_offline")
            results.append(cached)
            stats.cached_assessments_reused += 1
            continue
        logger.info("[SubscriptionAssessment][Refresh] user_id=%s merchant=%s reason=%s",
                    user_id, key, validation.reason)
        defaults = _defaults(user_id, group, heuristic, fingerprint, reference_date,
                             allow_llm, stats)
        try:
            with transaction.atomic():
                row, _ = SubscriptionAssessment.objects.update_or_create(
                    user_id=user_id, normalized_merchant=key, defaults=defaults)
        except IntegrityError:
            row = SubscriptionAssessment.objects.get(user_id=user_id, normalized_merchant=key)
            # A uniqueness race is safe to reuse only when the winning writer
            # persisted the exact snapshot this request was about to write.
            validation = validate_cached_assessment(
                row, fingerprint, required, llm_enabled, force=False
            )
            if not validation.valid:
                raise IntegrityError(
                    f"Concurrent assessment is stale: {validation.reason}"
                )
        logger.info("[SubscriptionAssessment][Persisted] user_id=%s merchant=%s "
                    "heuristic_classification=%s final_classification=%s "
                    "assessment_source=%s llm_status=%s", user_id, key,
                    row.heuristic_classification, row.final_classification,
                    row.assessment_source, row.llm_review_status)
        results.append(row)
        stats.stale_assessments_refreshed += 1
    if merchant_keys is None:
        active_keys = {group["normalized_merchant"] for group in groups}
        SubscriptionAssessment.objects.filter(user_id=user_id).exclude(
            normalized_merchant__in=active_keys).delete()
    results.sort(key=lambda item: item.normalized_merchant)
    counts = {name: sum(row.final_classification == name for row in results)
              for name in ("subscription", "not_subscription", "uncertain")}
    logger.info("[SubscriptionAssessment][Complete] user_id=%s cache_hits=%s refreshed=%s "
                "llm_attempted=%s llm_completed=%s llm_failed=%s subscriptions=%s "
                "not_subscriptions=%s uncertain=%s", user_id,
                stats.cached_assessments_reused, stats.stale_assessments_refreshed,
                stats.llm_reviews_attempted, stats.llm_reviews_completed,
                stats.llm_reviews_failed, counts["subscription"],
                counts["not_subscription"], counts["uncertain"])
    return AssessmentResult(results, stats)
