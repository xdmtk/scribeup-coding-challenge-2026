# Subscription Detection Process

The goal of this take-home is not simply to identify merchants that appear more than once. A repeated merchant is only a candidate for subscription detection. The broader task is to determine whether those transactions form a sufficiently consistent recurring pattern.

I am approaching the problem incrementally so that each assumption can be inspected against the seeded data before it becomes part of the final detection algorithm.

## Step 1: Group transactions by normalized merchant

The first step is to normalize merchant names and group transactions that appear to represent the same merchant.

For example, merchant values such as:

- `Netflix`
- `Netflix Inc`
- `NETFLIX.COM`

should be treated as one merchant group while preserving the original values for inspection.

At this stage, the transactions are divided into two broad categories:

- **Repeated merchants:** normalized merchants with two or more transactions.
- **Likely one-off merchants:** normalized merchants with only one transaction.

This is an exploratory classification only. A repeated merchant is not automatically considered a subscription.

The purpose of this view is to inspect the seeded data, validate the merchant normalization rules, and identify the patterns that distinguish actual subscriptions from repeated discretionary purchases.


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

## Step 3: Dominant cadence clusters and eligibility gates

The dataset-wide audit showed that obvious subscriptions frequently had no detected cadence:
the first detector was too strict for noisy monthly billing, while tiny samples could produce
misleading custom cadences. It also showed that identical recurring amounts did not distinguish
real subscriptions from discretionary purchases strongly enough.

This iteration scores the dominant cadence cluster using separate direct, skipped-cycle, and
outlier counts. Direct matches receive full support, two- and three-cycle skips receive decreasing
partial support, and a cadence must meet minimum direct and explained ratios. Monthly matching
combines bounded day intervals with calendar alignment. Amount evidence now considers exact
matches, coverage near the median, median deviation, and the maximum deviation. Custom cadences
require at least five transactions, and hard timing/history eligibility gates prevent amount,
history, or activity alone from creating a likely classification.

## Step 4: Sparse recurring candidates and evidence strength

The improved cadence detector handled long transaction histories well, but sparse and compelling
patterns were still forced into `unlikely`. This iteration separates **pattern quality** (how well
timing and amounts fit) from **evidence quantity** (how many direct observations and how much history
support that fit). A `possible` result now represents strong structural evidence for a named cadence
with insufficient history to establish recurrence confidently; the stricter `likely` gates remain in
place.

Sparse classification remains deterministic and offline. Two- and three-transaction candidates must
pass explicit cadence, direct-match, amount-consistency, and activity rules, and custom cadences cannot
qualify. These inspectable `possible` cases are also natural candidates for later semantic or LLM
review, without adding such review to the current classifier.
