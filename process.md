# Implementation process

## Step 2: Initial subscription analysis

Repeated merchant groups are now evaluated with a deterministic heuristic rather than being
treated as subscriptions merely because they occur more than once. Cadence is the strongest
signal: the analysis looks for stable weekly through yearly rhythms while allowing ordinary
billing-date drift and a small number of skipped observations.

Amount consistency supports that timing signal, but charges do not need to be exact. The number
of observations increases confidence up to a cap, and recency is evaluated relative to the
detected cadence so an old pattern is reduced rather than discarded. Each result exposes the
calculated timing, amount, history, and activity details along with concise positive and negative
evidence, making the classification inspectable.

This is an initial, deterministic heuristic—not a final or perfect subscription classifier.
## Auditing the subscription heuristic across seeded users

The existing deterministic heuristic is now audited across every seeded user before its scoring logic is changed. The audit is intended to expose possible false positives, false negatives, and borderline classifications in the supplied dataset. It reuses the exact merchant grouping and subscription-analysis code used by the UI, including each user's latest transaction date as the default reference date. Potentially suspicious results are highlighted for human review; a flag is diagnostic evidence, not an automatic conclusion that the algorithm failed. This phase is solely about validating current behavior against the supplied data.
