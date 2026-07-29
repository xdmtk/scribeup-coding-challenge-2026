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
