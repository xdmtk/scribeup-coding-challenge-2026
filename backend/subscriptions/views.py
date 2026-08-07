from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .merchant_groups import group_transactions
from .assessments import get_or_refresh_user_assessments
from .models import SubscriptionAssessment, Transaction
from .subscription_analysis import analyze_repeated_groups


def list_user_transactions(request, user_id: int):
    txns = Transaction.objects.filter(user_id=user_id).order_by("-charged_at")
    if not txns.exists():
        return JsonResponse({"error": "User not found"}, status=404)
    data = [
        {
            "id": t.id,
            "amount": str(t.amount),
            "merchant_name": t.merchant_name,
            "charged_at": t.charged_at.isoformat(),
            "raw_payload": t.raw_payload,
        }
        for t in txns
    ]
    return JsonResponse({"transactions": data})


@require_GET
def list_user_merchant_groups(request, user_id: int):
    txns = list(Transaction.objects.filter(user_id=user_id).order_by("-charged_at"))
    if not txns:
        return JsonResponse({"error": "User not found"}, status=404)

    repeated, one_off = group_transactions(txns)
    reference_date = max(transaction.charged_at.date() for transaction in txns)
    analysis = analyze_repeated_groups(repeated, reference_date)
    assessments = {
        row.normalized_merchant: row
        for row in SubscriptionAssessment.objects.filter(user_id=user_id)
    }

    # This endpoint remains deterministic and never triggers a semantic review.  A stored final
    # snapshot is included only to make the distinction visible to diagnostic clients.
    for category in analysis.values():
        for item in category:
            row = assessments.get(item["normalized_merchant"])
            if row:
                item["final_assessment"] = {
                    "final_classification": row.final_classification,
                    "assessment_source": row.assessment_source,
                    "llm_review_status": row.llm_review_status,
                    "updated_at": row.updated_at.isoformat(),
                }

    for group in repeated:
        del group["_transaction_objects"]

    return JsonResponse(
        {
            "user_id": user_id,
            "repeated_merchants": repeated,
            "likely_one_off_merchants": one_off,
            "subscription_analysis": analysis,
        }
    )


def list_users(request):
    user_ids = (
        Transaction.objects.values_list("user_id", flat=True).distinct().order_by("user_id")
    )
    return JsonResponse({"user_ids": list(user_ids)})


@require_GET
def list_user_subscriptions(request, user_id: int):
    result = get_or_refresh_user_assessments(user_id)
    if result is None:
        return JsonResponse({"error": "User not found"}, status=404)

    # The finalized endpoint exposes only confirmed subscriptions; diagnostic
    # classifications remain available through the merchant-groups endpoint.
    subscriptions = [
        {
            "merchant": row.display_merchant,
            "cadence": row.cadence,
            "typical_amount": f"{row.typical_amount:.2f}",
            "next_predicted_charge_date": (
                row.next_predicted_charge_date.isoformat() if row.next_predicted_charge_date else None
            ),
            "confidence": row.final_confidence,
            "assessment_source": row.assessment_source,
        }
        for row in result.assessments
        if row.final_classification == "subscription"
    ]
    stats = result.stats

    return JsonResponse(
        {
            "user_id": user_id,
            "subscriptions": subscriptions,
            "metadata": {
                "assessment_count": len(result.assessments),
                "subscription_count": len(subscriptions),
                "llm_reviews_used": stats.llm_reviews_completed,
                "cached_assessments_reused": stats.cached_assessments_reused,
                "stale_assessments_refreshed": stats.stale_assessments_refreshed,
            },
        }
    )
