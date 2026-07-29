from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .merchant_groups import group_transactions
from .models import Transaction
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
