# Implementation notes

- Synchronous semantic review on a first stale request is a take-home trade-off; production traffic
  might justify asynchronous jobs.
- SQLite is sufficient for this static dataset. Merchant-level invalidation minimizes API calls.
- Semantic review is intentionally selective: only `possible` candidates reach OpenAI.
- LLM output is persisted separately from heuristic evidence.
- Any OpenAI failure produces an `uncertain` result rather than a false decision.
- No Redis, Celery, worker, queue, or additional deployment infrastructure was added.

With more time I would add operational metrics and request coalescing for concurrent first hits, and
calibrate confidence against labeled data. AI assisted implementation and review; the policies,
boundaries, and tests remain explicit in the repository for human inspection.
