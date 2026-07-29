import re
from collections import defaultdict


LEGAL_OR_WEB_SUFFIXES = {"com", "inc", "llc", "corp", "corporation", "ltd", "co"}


def normalize_merchant(name: str) -> str:
    """Return a conservative identity key for a merchant descriptor."""
    words = re.findall(r"[\w]+", name.casefold().strip(), flags=re.UNICODE)
    while len(words) > 1 and words[-1] in LEGAL_OR_WEB_SUFFIXES:
        words.pop()
    return " ".join(words)


def group_transactions(transactions):
    grouped = defaultdict(list)
    for transaction in transactions:
        grouped[normalize_merchant(transaction.merchant_name)].append(transaction)

    groups = []
    for normalized_merchant, merchant_transactions in grouped.items():
        merchant_transactions.sort(key=lambda transaction: transaction.charged_at, reverse=True)
        variants = list(dict.fromkeys(transaction.merchant_name for transaction in merchant_transactions))
        groups.append(
            {
                "normalized_merchant": normalized_merchant,
                "display_merchant": variants[0],
                "merchant_variants": variants,
                "transaction_count": len(merchant_transactions),
                "transactions": [
                    {
                        "id": transaction.id,
                        "amount": str(transaction.amount),
                        "merchant_name": transaction.merchant_name,
                        "charged_at": transaction.charged_at.isoformat(),
                        "raw_payload": transaction.raw_payload,
                    }
                    for transaction in merchant_transactions
                ],
                "_transaction_objects": merchant_transactions,
                "_most_recent": merchant_transactions[0].charged_at,
            }
        )

    repeated = [group for group in groups if group["transaction_count"] >= 2]
    one_off = [group for group in groups if group["transaction_count"] == 1]
    repeated.sort(key=lambda group: (-group["transaction_count"], group["normalized_merchant"]))
    one_off.sort(key=lambda group: group["_most_recent"], reverse=True)
    for group in one_off:
        del group["_transaction_objects"]
    for group in groups:
        del group["_most_recent"]

    return repeated, one_off
