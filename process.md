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


