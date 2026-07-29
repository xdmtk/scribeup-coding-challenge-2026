"""Deterministic, inspectable heuristics for recurring merchant groups."""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from statistics import median


# Classification is intentionally conservative: repetition alone is not enough.
LIKELY_SUBSCRIPTION_THRESHOLD = 0.68
SCORE_WEIGHTS = {"timing": 0.55, "amount": 0.22, "history": 0.15, "activity": 0.08}

# label, target days, allowed processing/billing-date drift
CADENCE_BUCKETS = (
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("every four weeks", 28, 2),
    ("bimonthly", 61, 5),
    ("quarterly", 91, 7),
    ("semiannual", 182, 10),
    ("yearly", 365, 15),
)


def _interval_fit(intervals, target, tolerance):
    """Score intervals, allowing a conservative two/three-cycle missing charge."""
    fits = []
    for interval in intervals:
        choices = [abs(interval - target * multiple) for multiple in (1, 2, 3)]
        difference = min(choices)
        multiple = choices.index(difference) + 1
        allowed = tolerance * multiple
        # Prefer a direct cadence match over explaining every interval as a
        # missing observation from a shorter cadence.
        multiple_penalty = {1: 1.0, 2: 0.85, 3: 0.72}[multiple]
        fits.append(max(0.0, 1.0 - difference / allowed) * multiple_penalty)
    return sum(fits) / len(fits)


def _calendar_monthly_fit(dates):
    fits = []
    for earlier, later in zip(dates, dates[1:]):
        months = (later.year - earlier.year) * 12 + later.month - earlier.month
        if months not in (1, 2, 3):
            fits.append(0.0)
            continue
        # End-of-month charges remain aligned even when month lengths differ.
        earlier_end = earlier.day == monthrange(earlier.year, earlier.month)[1]
        later_end = later.day == monthrange(later.year, later.month)[1]
        day_drift = 0 if earlier_end and later_end else abs(later.day - earlier.day)
        fits.append(max(0.0, 1.0 - day_drift / 4.0))
    return sum(fits) / len(fits)


def detect_cadence(dates):
    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    candidates = [
        {"label": label, "target": target, "tolerance": tolerance,
         "score": _interval_fit(intervals, target, tolerance)}
        for label, target, tolerance in CADENCE_BUCKETS
    ]
    candidates.append(
        {"label": "monthly", "target": 30, "tolerance": 4,
         "score": _calendar_monthly_fit(dates)}
    )
    best = max(candidates, key=lambda candidate: candidate["score"])

    # A single interval is inherently weak evidence, however perfect it looks.
    support = min(1.0, len(intervals) / 3)
    consistency = best["score"] * (0.65 + 0.35 * support)
    typical = int(round(median(intervals)))

    if best["score"] < 0.55 and len(intervals) >= 2 and typical > 0:
        deviations = [abs(value - typical) for value in intervals]
        custom_score = max(0.0, 1.0 - float(median(deviations)) / max(typical * 0.2, 2))
        if custom_score >= 0.75:
            best = {"label": f"every_{typical}_days", "target": typical,
                    "tolerance": max(2, round(typical * 0.1)), "score": custom_score}
            consistency = custom_score * (0.65 + 0.35 * support)

    named = best if best["score"] >= 0.55 else None
    return {
        "label": named["label"] if named else None,
        "typical_interval_days": typical,
        "intervals_days": intervals,
        "consistency_score": round(min(1.0, consistency), 3),
        "target_interval_days": named["target"] if named else None,
        "tolerance_days": named["tolerance"] if named else None,
    }


def analyze_amounts(transactions):
    amounts = [transaction.amount for transaction in transactions]
    typical = median(amounts)
    deviations = [abs(amount - typical) for amount in amounts]
    if typical == 0:
        relative_variation = Decimal("0") if all(amount == 0 for amount in amounts) else Decimal("1")
    else:
        relative_variation = median(deviations) / abs(typical)
    consistency = max(Decimal("0"), Decimal("1") - relative_variation / Decimal("0.50"))
    return {
        "typical_amount": str(typical.quantize(Decimal("0.01"))),
        "min_amount": str(min(amounts).quantize(Decimal("0.01"))),
        "max_amount": str(max(amounts).quantize(Decimal("0.01"))),
        "relative_variation": round(float(relative_variation), 3),
        "consistency_score": round(float(consistency), 3),
    }


def _activity(cadence, latest_date, reference_date):
    expected = cadence["target_interval_days"] or cadence["typical_interval_days"]
    age = max(0, (reference_date - latest_date).days)
    if not expected or expected <= 0:
        return 0.5, False, age
    cycles_late = age / expected
    if cycles_late <= 1.5:
        return 1.0, True, age
    if cycles_late <= 2.5:
        return 0.6, True, age
    return 0.1, False, age


def _evidence(cadence, amounts, count, active):
    messages = []
    if cadence["label"] and cadence["consistency_score"] >= 0.7:
        messages.append({"type": "positive", "label": f"Stable {cadence['label']} cadence"})
    else:
        messages.append({"type": "negative", "label": "No stable interval between charges"})
    if amounts["relative_variation"] == 0:
        messages.append({"type": "positive", "label": f"Amounts are identical across {count} charges"})
    elif amounts["consistency_score"] >= 0.7:
        messages.append({"type": "positive", "label": "Amounts remain within a narrow range"})
    elif amounts["consistency_score"] < 0.35:
        messages.append({"type": "negative", "label": "Amounts vary substantially"})
    if count == 2:
        messages.append({"type": "negative", "label": "Only two observations are available"})
    elif count >= 3:
        messages.append({"type": "positive", "label": f"{count} historical transactions support the pattern"})
    target = cadence["target_interval_days"]
    if target and any(interval < target * 0.45 for interval in cadence["intervals_days"]):
        messages.append({"type": "negative", "label": "Several transactions occur within the same expected billing period"})
    messages.append({"type": "positive" if active else "negative",
                     "label": "Most recent charge matches the expected schedule" if active else "Pattern appears inactive"})
    return messages


def analyze_merchant_group(group, reference_date: date):
    transactions = sorted(group["_transaction_objects"], key=lambda transaction: transaction.charged_at)
    dates = [transaction.charged_at.date() for transaction in transactions]
    cadence = detect_cadence(dates)
    amounts = analyze_amounts(transactions)
    count = len(transactions)
    history_score = min(1.0, max(0.2, (count - 1) / 5))
    activity_score, active, age = _activity(cadence, dates[-1], reference_date)
    score = (
        SCORE_WEIGHTS["timing"] * cadence["consistency_score"]
        + SCORE_WEIGHTS["amount"] * amounts["consistency_score"]
        + SCORE_WEIGHTS["history"] * history_score
        + SCORE_WEIGHTS["activity"] * activity_score
    )
    # Two points cannot establish recurrence, regardless of a coincidental match.
    if count == 2:
        score = min(score, 0.64)
    score = round(max(0.0, min(1.0, score)), 3)
    result = {key: value for key, value in group.items() if key != "_transaction_objects"}
    result.update({
        "classification": "likely" if score >= LIKELY_SUBSCRIPTION_THRESHOLD else "unlikely",
        "confidence_score": score,
        "detected_cadence": cadence,
        "amount_analysis": amounts,
        "activity": {"apparently_active": active, "days_since_last_charge": age},
        "evidence": _evidence(cadence, amounts, count, active),
    })
    return result


def analyze_repeated_groups(groups, reference_date: date):
    analyzed = [analyze_merchant_group(group, reference_date) for group in groups]
    likely = sorted((item for item in analyzed if item["classification"] == "likely"),
                    key=lambda item: item["confidence_score"], reverse=True)
    unlikely = sorted((item for item in analyzed if item["classification"] == "unlikely"),
                      key=lambda item: item["confidence_score"], reverse=True)
    return {"likely_subscriptions": likely, "unlikely_subscriptions": unlikely}
