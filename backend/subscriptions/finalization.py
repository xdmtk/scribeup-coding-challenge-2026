"""Central policy for turning structural analysis into final decisions."""


def requires_llm_review(heuristic_result):
    # Deliberately conservative: only the heuristic's explicit ambiguous bucket.
    return heuristic_result["classification"] == "possible"


def offline_decision(heuristic_result):
    classification = heuristic_result["classification"]
    confidence = heuristic_result["confidence_score"]
    if classification == "likely":
        return "subscription", confidence, "Strong deterministic recurring pattern."
    if classification == "unlikely":
        return "not_subscription", 1 - confidence, "Deterministic evidence does not support recurrence."
    return "uncertain", confidence, "Semantic review is unavailable for this ambiguous pattern."
