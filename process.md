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
