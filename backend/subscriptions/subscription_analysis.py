"""Deterministic, inspectable heuristics for recurring merchant groups."""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from statistics import median


LIKELY_SUBSCRIPTION_THRESHOLD = 0.68
SCORE_WEIGHTS = {"timing": 0.50, "amount": 0.30, "history": 0.15, "activity": 0.05}

# A returned cadence is a dominant cluster, not a requirement that every gap fit.
MIN_DIRECT_MATCH_RATIO = 0.50
MIN_EXPLAINED_RATIO = 0.70
MIN_TIMING_CONSISTENCY = 0.65
MIN_CUSTOM_TRANSACTIONS = 5
MIN_CUSTOM_DIRECT_RATIO = 0.75

# Classification gates are deliberately separate from the compatibility score.
# Sparse candidates must match one of these understood cadences; a fitted custom
# interval is never sufficient evidence for ``possible``.
NAMED_CADENCES = frozenset((
    "weekly", "biweekly", "every four weeks", "monthly", "bimonthly",
    "quarterly", "semiannual", "yearly",
))
POSSIBLE_TWO_MIN_TIMING = 0.75
POSSIBLE_TWO_MIN_AMOUNT = 0.95
POSSIBLE_THREE_MIN_TIMING = 0.60
POSSIBLE_THREE_MIN_AMOUNT = 0.90
LIKELY_THREE_MIN_TIMING = 0.87
LIKELY_THREE_MIN_AMOUNT = 0.70

# label, target days, direct-match tolerance. Monthly has calendar-specific rules.
CADENCE_BUCKETS = (
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("every four weeks", 28, 2),
    ("monthly", 30, 5),
    ("bimonthly", 61, 5),
    ("quarterly", 91, 7),
    # Twelve days accommodates processing drift around six-month renewals. Sparse
    # eligibility still requires direct matches, so this cannot explain skips.
    ("semiannual", 182, 12),
    ("yearly", 365, 15),
)


def _month_distance(earlier, later):
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _monthly_alignment(earlier, later, cycles):
    if _month_distance(earlier, later) != cycles:
        return False
    earlier_end = earlier.day >= monthrange(earlier.year, earlier.month)[1] - 2
    later_end = later.day >= monthrange(later.year, later.month)[1] - 2
    return (earlier_end and later_end) or abs(later.day - earlier.day) <= 5


def _classify_interval(label, target, tolerance, interval, earlier, later):
    """Return cycle multiple and deviation; direct matches always outrank skips."""
    if label == "monthly":
        # Calendar billing commonly moves by several days because of month length,
        # weekends, and processing. Keep explicit bounds so random gaps do not fit.
        windows = {1: (25, 35), 2: (52, 66), 3: (80, 97)}
        for cycles, (low, high) in windows.items():
            if low <= interval <= high or _monthly_alignment(earlier, later, cycles):
                return cycles, abs(interval - target * cycles) / cycles
        return None, None
    for cycles in (1, 2, 3):
        deviation = abs(interval - target * cycles)
        if deviation <= tolerance * cycles:
            return cycles, deviation / cycles
    return None, None


def _candidate_metrics(dates, label, target, tolerance):
    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    matches = [_classify_interval(label, target, tolerance, interval, earlier, later)
               for interval, earlier, later in zip(intervals, dates, dates[1:])]
    direct_deviations = [deviation for (cycles, deviation) in matches if cycles == 1]
    direct = len(direct_deviations)
    skipped_two = sum(cycles == 2 for cycles, _ in matches)
    skipped_three = sum(cycles == 3 for cycles, _ in matches)
    skipped = skipped_two + skipped_three
    total = len(intervals)
    explained = direct + skipped
    direct_ratio = direct / total
    explained_ratio = explained / total
    deviation = float(median(direct_deviations)) if direct_deviations else None
    deviation_quality = 0 if deviation is None else max(0, 1 - deviation / tolerance)
    weighted_support = (direct + .55 * skipped_two + .35 * skipped_three) / total
    observation_support = min(1, total / 4)
    consistency = (.75 * weighted_support + .15 * explained_ratio +
                   .10 * deviation_quality) * (.80 + .20 * observation_support)

    # A true four-week schedule drifts through the calendar. Conversely, recurring
    # day-of-month/end-of-month alignment breaks otherwise close monthly/28-day ties.
    calendar_aligned = sum(_monthly_alignment(a, b, 1) for a, b in zip(dates, dates[1:])) / total
    exact_four_week_ratio = sum(abs(interval - 28) <= 1 for interval in intervals) / total
    if label == "monthly":
        consistency += .04 * calendar_aligned
        if exact_four_week_ratio >= .75 and max(day.day for day in dates) - min(day.day for day in dates) >= 5:
            consistency -= .10
    elif label == "every four weeks" and calendar_aligned >= .75:
        consistency -= .05
        if exact_four_week_ratio >= .75:
            consistency += .08

    return {
        "label": label, "target": target, "tolerance": tolerance,
        "direct_match_count": direct, "skipped_match_count": skipped,
        "two_cycle_skip_count": skipped_two, "three_cycle_skip_count": skipped_three,
        "outlier_count": total - explained,
        "direct_match_ratio": direct_ratio, "explained_ratio": explained_ratio,
        "median_direct_deviation_days": deviation,
        "consistency_score": max(0, min(1, consistency)),
    }


def _custom_candidate(intervals):
    typical = int(round(median(intervals)))
    tolerance = max(2, round(typical * .10))
    deviations = [abs(value - typical) for value in intervals]
    direct = sum(value <= tolerance for value in deviations)
    direct_ratio = direct / len(intervals)
    relative_dispersion = float(median(deviations)) / typical if typical else 1
    if direct_ratio < MIN_CUSTOM_DIRECT_RATIO or relative_dispersion > .10:
        return None
    deviation = float(median(value for value in deviations if value <= tolerance))
    consistency = min(.88, .72 * direct_ratio + .18 * (1 - relative_dispersion) +
                      .10 * min(1, len(intervals) / 8))
    return {
        "label": f"every_{typical}_days", "target": typical, "tolerance": tolerance,
        "direct_match_count": direct, "skipped_match_count": 0,
        "two_cycle_skip_count": 0, "three_cycle_skip_count": 0,
        "outlier_count": len(intervals) - direct, "direct_match_ratio": direct_ratio,
        "explained_ratio": direct_ratio, "median_direct_deviation_days": deviation,
        "consistency_score": consistency,
    }


def detect_cadence(dates):
    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    typical = int(round(median(intervals)))
    candidates = [_candidate_metrics(dates, *bucket) for bucket in CADENCE_BUCKETS]
    eligible = [candidate for candidate in candidates
                if candidate["direct_match_ratio"] >= MIN_DIRECT_MATCH_RATIO
                and candidate["explained_ratio"] >= MIN_EXPLAINED_RATIO]
    best = max(eligible, key=lambda candidate: (candidate["consistency_score"],
                                                candidate["direct_match_ratio"]), default=None)
    custom_history_insufficient = False
    if best is None:
        if len(dates) >= MIN_CUSTOM_TRANSACTIONS:
            best = _custom_candidate(intervals)
        else:
            custom_history_insufficient = len(intervals) >= 2 and typical > 0

    empty = {"direct_match_count": 0, "skipped_match_count": 0,
             "two_cycle_skip_count": 0, "three_cycle_skip_count": 0,
             "outlier_count": len(intervals), "direct_match_ratio": 0.0,
             "explained_ratio": 0.0, "median_direct_deviation_days": None,
             "consistency_score": 0.0}
    metrics = best or empty
    return {
        "label": best["label"] if best else None,
        "typical_interval_days": typical, "intervals_days": intervals,
        "consistency_score": round(metrics["consistency_score"], 3),
        "target_interval_days": best["target"] if best else None,
        "tolerance_days": best["tolerance"] if best else None,
        "direct_match_count": metrics["direct_match_count"],
        "skipped_match_count": metrics["skipped_match_count"],
        "outlier_count": metrics["outlier_count"],
        "direct_match_ratio": round(metrics["direct_match_ratio"], 3),
        "explained_ratio": round(metrics["explained_ratio"], 3),
        "median_direct_deviation_days": metrics["median_direct_deviation_days"],
        "two_cycle_skip_count": metrics["two_cycle_skip_count"],
        "three_cycle_skip_count": metrics["three_cycle_skip_count"],
        "custom_history_insufficient": custom_history_insufficient,
    }


def analyze_amounts(transactions):
    amounts = [transaction.amount for transaction in transactions]
    typical = median(amounts)
    denominator = abs(typical)
    relative = ([abs(amount - typical) / denominator for amount in amounts]
                if denominator else [Decimal("0") if amount == 0 else Decimal("1") for amount in amounts])
    within_five = sum(value <= Decimal(".05") for value in relative) / len(relative)
    within_fifteen = sum(value <= Decimal(".15") for value in relative) / len(relative)
    exact = sum(amount == typical for amount in amounts) / len(amounts)
    median_relative = median(relative)
    maximum_relative = max(relative)
    # Broad coverage prevents a zero median deviation from hiding extreme tails.
    consistency = (.30 * within_five + .20 * within_fifteen + .20 * exact +
                   .10 * max(0, 1 - float(median_relative) / .30) +
                   .20 * max(0, 1 - float(maximum_relative) / .75))
    return {
        "typical_amount": str(typical.quantize(Decimal("0.01"))),
        "min_amount": str(min(amounts).quantize(Decimal("0.01"))),
        "max_amount": str(max(amounts).quantize(Decimal("0.01"))),
        "relative_variation": round(float(median_relative), 3),
        "median_relative_deviation": round(float(median_relative), 3),
        "maximum_relative_deviation": round(float(maximum_relative), 3),
        "within_five_percent_ratio": round(within_five, 3),
        "within_fifteen_percent_ratio": round(within_fifteen, 3),
        "exact_match_ratio": round(exact, 3),
        "consistency_score": round(max(0, min(1, consistency)), 3),
    }


def _activity(cadence, latest_date, reference_date):
    age = max(0, (reference_date - latest_date).days)
    if not cadence["label"]:
        return 0.0, None, age
    expected = cadence["target_interval_days"]
    cycles_late = age / expected
    if cycles_late <= 1.5:
        return 1.0, True, age
    if cycles_late <= 2.5:
        return .6, True, age
    return .1, False, age


def _pattern_quality(cadence, amounts):
    """Structural fit, not a calibrated probability."""
    return round(max(0, min(1,
        .45 * cadence["consistency_score"] +
        .25 * cadence["direct_match_ratio"] +
        .10 * cadence["explained_ratio"] +
        .20 * amounts["consistency_score"])), 3)


def _evidence_strength(cadence, count, dates):
    """Quantity of support: count 55%, intervals 20%, directness 15%, span 10%.

    The count curve is intentionally conservative: 2=.25, 3=.40, 4=.60,
    5=.72, then +.07 per observation to a maximum of 1.0.
    """
    count_support = {2: .25, 3: .40, 4: .60}.get(count, min(1, .72 + .07 * (count - 5)))
    intervals = max(1, count - 1)
    interval_support = min(1, intervals / 4)
    direct_support = ((cadence["direct_match_count"] +
                       .5 * cadence["skipped_match_count"]) / intervals
                      if cadence["label"] else 0)
    target = cadence["target_interval_days"]
    duration_support = min(1, (dates[-1] - dates[0]).days / target) if target else 0
    return round(max(0, min(1, .55 * count_support + .20 * interval_support +
                             .15 * direct_support + .10 * duration_support)), 3)


def _qualifies_for_likely(count, cadence, amounts, score):
    base = (count >= 3 and cadence["label"] is not None
            and cadence["consistency_score"] >= MIN_TIMING_CONSISTENCY
            and cadence["direct_match_ratio"] >= MIN_DIRECT_MATCH_RATIO
            and score >= LIKELY_SUBSCRIPTION_THRESHOLD)
    if not base:
        return False
    if count >= 4:
        return True
    # Three observations are enough only when both intervals are direct and the
    # cadence and amounts are exceptionally clean.
    return (cadence["label"] in NAMED_CADENCES
            and cadence["direct_match_ratio"] == 1.0
            and cadence["explained_ratio"] == 1.0
            and cadence["consistency_score"] >= LIKELY_THREE_MIN_TIMING
            and amounts["consistency_score"] >= LIKELY_THREE_MIN_AMOUNT)


def _qualifies_for_possible(count, cadence, amounts, active):
    if cadence["label"] not in NAMED_CADENCES or active is False:
        return False
    if count == 2:
        return (cadence["direct_match_count"] == 1
                and cadence["skipped_match_count"] == 0
                and cadence["direct_match_ratio"] == 1.0
                and cadence["explained_ratio"] == 1.0
                and cadence["consistency_score"] >= POSSIBLE_TWO_MIN_TIMING
                and amounts["exact_match_ratio"] == 1.0
                and amounts["consistency_score"] >= POSSIBLE_TWO_MIN_AMOUNT)
    if count == 3:
        nearly_identical = (amounts["within_five_percent_ratio"] == 1.0
                            and amounts["maximum_relative_deviation"] <= .05)
        return (cadence["direct_match_ratio"] >= .50
                and cadence["explained_ratio"] == 1.0
                and cadence["direct_match_count"] >= 1
                and cadence["consistency_score"] >= POSSIBLE_THREE_MIN_TIMING
                and nearly_identical
                and amounts["consistency_score"] >= POSSIBLE_THREE_MIN_AMOUNT)
    return False


def _evidence(cadence, amounts, count, active, classification):
    messages = []
    if cadence["label"]:
        if classification == "possible":
            if count == 2:
                cadence_message = f"Observed interval directly matches a {cadence['label']} cadence"
            elif cadence["direct_match_count"] == count - 1:
                cadence_message = f"Both observed intervals support a {cadence['label']} cadence"
            else:
                cadence_message = f"Observed intervals are compatible with a {cadence['label']} cadence"
            messages.append({"type": "positive", "label": cadence_message})
        else:
            messages.append({"type": "positive", "label": f"Stable {cadence['label']} cadence"})
        if cadence["direct_match_ratio"] >= .75 and classification != "possible":
            messages.append({"type": "positive", "label": f"Most intervals match a {cadence['label']} cadence"})
        if cadence["skipped_match_count"]:
            noun = "interval may" if cadence["skipped_match_count"] == 1 else "intervals may"
            messages.append({"type": "positive", "label": f"{cadence['skipped_match_count']} {noun} represent skipped charges"})
    else:
        messages.append({"type": "negative", "label": "No stable interval between charges"})
        if cadence["custom_history_insufficient"]:
            messages.append({"type": "negative", "label": "Insufficient history to establish a custom cadence"})
    if amounts["exact_match_ratio"] == 1:
        messages.append({"type": "positive", "label": f"Amounts are identical across {count} charges"})
    elif amounts["consistency_score"] >= .7:
        messages.append({"type": "positive", "label": "Amounts remain within a narrow range"})
    elif amounts["consistency_score"] < .35:
        messages.append({"type": "negative", "label": "Amounts vary substantially"})
    if count <= 3:
        messages.append({"type": "negative", "label": f"Only {count} observations are available"})
        if classification == "possible":
            messages.append({"type": "positive", "label": "Pattern quality is strong despite limited history"})
            messages.append({"type": "negative", "label": "More history is needed to confirm recurrence"})
    elif count >= 5:
        messages.append({"type": "positive", "label": f"{count} historical transactions strongly support the pattern"})
    if active is not None:
        messages.append({"type": "positive" if active else "negative",
                         "label": "Most recent charge matches the expected schedule" if active else "Pattern appears inactive"})
    return messages


def analyze_merchant_group(group, reference_date: date):
    transactions = sorted(group["_transaction_objects"], key=lambda transaction: transaction.charged_at)
    dates = [transaction.charged_at.date() for transaction in transactions]
    cadence, amounts = detect_cadence(dates), analyze_amounts(transactions)
    count = len(transactions)
    history_score = min(1.0, max(.2, (count - 1) / 5))
    activity_score, active, age = _activity(cadence, dates[-1], reference_date)
    score = sum((SCORE_WEIGHTS["timing"] * cadence["consistency_score"],
                 SCORE_WEIGHTS["amount"] * amounts["consistency_score"],
                 SCORE_WEIGHTS["history"] * history_score,
                 SCORE_WEIGHTS["activity"] * activity_score))
    if count == 2:
        score = min(score, .64)
    score = round(max(0, min(1, score)), 3)
    pattern_quality = _pattern_quality(cadence, amounts)
    evidence_strength = _evidence_strength(cadence, count, dates)
    if _qualifies_for_likely(count, cadence, amounts, score):
        classification = "likely"
    elif _qualifies_for_possible(count, cadence, amounts, active):
        classification = "possible"
    else:
        classification = "unlikely"
    result = {key: value for key, value in group.items() if key != "_transaction_objects"}
    result.update({
        "classification": classification, "confidence_score": score,
        "pattern_quality_score": pattern_quality,
        "evidence_strength_score": evidence_strength,
        "detected_cadence": cadence, "amount_analysis": amounts,
        "activity": {"apparently_active": active, "days_since_last_charge": age},
        "evidence": _evidence(cadence, amounts, count, active, classification),
    })
    return result


def analyze_repeated_groups(groups, reference_date: date):
    analyzed = [analyze_merchant_group(group, reference_date) for group in groups]
    likely = sorted((item for item in analyzed if item["classification"] == "likely"),
                    key=lambda item: item["confidence_score"], reverse=True)
    possible = sorted((item for item in analyzed if item["classification"] == "possible"),
                      key=lambda item: (item["pattern_quality_score"], item["confidence_score"]),
                      reverse=True)
    unlikely = sorted((item for item in analyzed if item["classification"] == "unlikely"),
                      key=lambda item: item["confidence_score"], reverse=True)
    return {"likely_subscriptions": likely, "possible_subscriptions": possible,
            "unlikely_subscriptions": unlikely}
