"""Reporting helpers for auditing the existing subscription heuristic."""

import json
from collections import OrderedDict

from .subscription_analysis import LIKELY_SUBSCRIPTION_THRESHOLD


NEGATIVE_INTERVAL_EVIDENCE = "No stable interval between charges"
BUCKETS = ((0, .25, "0.00–0.24"), (.25, .50, "0.25–0.49"),
           (.50, .68, "0.50–0.67"), (.68, .85, "0.68–0.84"),
           (.85, 1.001, "0.85–1.00"))


def _has_evidence(item, label):
    return any(evidence["label"] == label for evidence in item["evidence"])


def suspicious_reasons(item):
    cadence = item["detected_cadence"]
    amount = item["amount_analysis"]
    count = item["transaction_count"]
    reasons = []
    if cadence["label"] and _has_evidence(item, NEGATIVE_INTERVAL_EVIDENCE):
        reasons.append("cadence label conflicts with evidence")
    if count == 2 and item["confidence_score"] >= .50:
        reasons.append("two observations with confidence >= 0.50")
    if item["classification"] == "likely" and cadence["consistency_score"] < .65:
        reasons.append("likely despite low timing consistency")
    if item["classification"] == "likely" and not cadence["label"]:
        reasons.append("likely with no detected cadence")
    if item["classification"] == "likely" and not item["activity"]["apparently_active"]:
        reasons.append("likely but apparently inactive")
    if amount["consistency_score"] >= .90 and cadence["consistency_score"] < .40:
        reasons.append("high amount consistency but low timing consistency")
    if cadence["consistency_score"] >= .85 and item["classification"] == "unlikely":
        reasons.append("high timing consistency but unlikely")
    if cadence["label"] and cadence["label"].startswith("every_") and count < 4:
        reasons.append("custom cadence from fewer than four transactions")
    if abs(item["confidence_score"] - LIKELY_SUBSCRIPTION_THRESHOLD) <= .05:
        reasons.append("confidence within 0.05 of threshold")
    return reasons


def build_report(users, total_transactions):
    """Build deterministic aggregate and review sections from analyzed users."""
    rows = [(user["user_id"], item) for user in users for category in
            ("likely_subscriptions", "unlikely_subscriptions") for item in user[category]]
    items = [item for _, item in rows]
    contradictions = sum(bool(item["detected_cadence"]["label"]) and
                         _has_evidence(item, NEGATIVE_INTERVAL_EVIDENCE) for item in items)
    buckets = OrderedDict((label, sum(low <= item["confidence_score"] < high for item in items))
                          for low, high, label in BUCKETS)
    summary = OrderedDict([
        ("total_users", len(users)), ("total_transactions", total_transactions),
        ("total_repeated_merchant_groups", len(items)),
        ("total_likely_subscriptions", sum(i["classification"] == "likely" for i in items)),
        ("total_unlikely_subscriptions", sum(i["classification"] == "unlikely" for i in items)),
        ("groups_with_exactly_two_transactions", sum(i["transaction_count"] == 2 for i in items)),
        ("likely_with_exactly_two_transactions", sum(i["classification"] == "likely" and i["transaction_count"] == 2 for i in items)),
        ("cadence_evidence_contradictions", contradictions),
        ("groups_with_no_detected_cadence", sum(not i["detected_cadence"]["label"] for i in items)),
        ("apparently_inactive_groups", sum(not i["activity"]["apparently_active"] for i in items)),
        ("confidence_buckets", buckets),
    ])
    borderline = [{"user_id": uid, **item} for uid, item in rows
                  if abs(item["confidence_score"] - LIKELY_SUBSCRIPTION_THRESHOLD) <= .10]
    borderline.sort(key=lambda i: (abs(i["confidence_score"] - LIKELY_SUBSCRIPTION_THRESHOLD),
                                   i["user_id"], i["normalized_merchant"]))
    suspicious = []
    for uid, item in rows:
        reasons = suspicious_reasons(item)
        if reasons:
            suspicious.append({"user_id": uid, **item, "suspicious_reasons": reasons})
    suspicious.sort(key=lambda i: (i["user_id"], i["normalized_merchant"]))
    return {"summary": summary, "borderline_cases": borderline,
            "suspicious_cases": suspicious, "users": users}


def _money(value):
    return f"${float(value):,.2f}"


def _case_line(item, suspicious=False):
    cadence = item["detected_cadence"]["label"] or "no cadence"
    base = (f"User {item['user_id']} | {item['display_merchant']} | "
            f"{item['confidence_score']:.2f} {item['classification']} | {cadence} | "
            f"{item['transaction_count']} txns")
    return base + (" | " + "; ".join(item["suspicious_reasons"]) if suspicious else "")


def _render_group(item, index, max_transactions):
    cadence, amounts = item["detected_cadence"], item["amount_analysis"]
    transactions = item["transactions"]
    shown = transactions[:max_transactions] if max_transactions is not None else transactions
    lines = [f"[{index}] {item['display_merchant']}",
             f"classification: {item['classification']}", f"confidence: {item['confidence_score']:.3f}",
             f"transactions: {item['transaction_count']}",
             f"normalized_merchant: {item['normalized_merchant']}"]
    if len(item["merchant_variants"]) > 1:
        lines.append("merchant_variants: " + ", ".join(item["merchant_variants"]))
    lines += [f"cadence: {cadence['label'] or 'none'}",
              f"typical_interval_days: {cadence['typical_interval_days']}",
              "intervals_days: " + ", ".join(map(str, cadence["intervals_days"])),
              f"timing_consistency: {cadence['consistency_score']:.3f}",
              f"typical_amount: {_money(amounts['typical_amount'])}",
              f"amount_range: {_money(amounts['min_amount'])}–{_money(amounts['max_amount'])}",
              f"relative_amount_variation: {amounts['relative_variation']:.3f}",
              f"apparently_active: {str(item['activity']['apparently_active']).lower()}",
              f"days_since_last_charge: {item['activity']['days_since_last_charge']}"]
    if len(shown) < len(transactions):
        lines.append("transactions_truncated: true")
    lines.append("evidence:")
    lines.extend(f"  {'+' if e['type'] == 'positive' else '-'} {e['label']}" for e in item["evidence"])
    lines.append("transactions:")
    lines.extend(f"  {txn['charged_at'][:10]} | {txn['merchant_name']} | {_money(txn['amount'])}" for txn in shown)
    return "\n".join(lines)


def render_text(report, borderline_only=False, max_transactions=None):
    summary = report["summary"]
    lines = ["=" * 60, "GLOBAL SUMMARY", "=" * 60]
    for key, value in summary.items():
        if key != "confidence_buckets":
            lines.append(f"{key}: {value}")
    lines.append("confidence_buckets:")
    lines.extend(f"  {key}: {value}" for key, value in summary["confidence_buckets"].items())
    lines += ["", "POTENTIALLY SUSPICIOUS RESULTS"]
    lines.extend(_case_line(item, True) for item in report["suspicious_cases"])
    if not report["suspicious_cases"]: lines.append("None")
    lines += ["", "GLOBAL BORDERLINE CASES"]
    lines.extend(_case_line(item) for item in report["borderline_cases"])
    if not report["borderline_cases"]: lines.append("None")
    if not borderline_only:
        for user in report["users"]:
            lines += ["", "=" * 60, f"USER {user['user_id']}", "=" * 60]
            for key, heading in (("likely_subscriptions", "LIKELY SUBSCRIPTIONS"),
                                 ("unlikely_subscriptions", "UNLIKELY SUBSCRIPTIONS")):
                lines += ["", heading, ""]
                if not user[key]: lines.append("None")
                for index, item in enumerate(user[key], 1):
                    lines += [_render_group(item, index, max_transactions), ""]
    return "\n".join(lines).rstrip() + "\n"


def render_json(report, borderline_only=False):
    data = dict(report)
    if borderline_only:
        data["users"] = []
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
