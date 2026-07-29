from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .merchant_groups import group_transactions
from .models import Transaction


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
    return JsonResponse(
        {
            "user_id": user_id,
            "repeated_merchants": repeated,
            "likely_one_off_merchants": one_off,
        }
    )


def list_users(request):
    user_ids = (
        Transaction.objects.values_list("user_id", flat=True).distinct().order_by("user_id")
    )
    return JsonResponse({"user_ids": list(user_ids)})
