# Project Summary and Portfolio Bullets

## One-paragraph summary

Built an end-to-end forecasting research pipeline testing whether
commodity and refinery input prices improve one- and three-month-ahead
industrial-stress forecasts for twelve Thai manufacturing industries,
using official production, price and input-output statistics. The system
enforces publication-time availability at every step, derives industry
exposure from national input-output accounts, and evaluates candidates
walk-forward against registered baselines with clustered bootstrap
uncertainty and decision rules fixed before any outcome was read. No
candidate improved on the persistence baseline on development data, so
the study concludes with a baseline-only reference and a final test that
was deliberately never opened.

## CV bullets

* Built a leakage-aware forecasting pipeline over four official
  statistical sources, enforcing publication-time availability with
  archived first-release vintages, per-forecast issue-date contracts and
  automated guards that fail the run rather than warn.
* Derived reproducible industry-exposure matrices from national
  input-output accounts and evaluated candidate models walk-forward with
  issue-month clustered bootstrap uncertainty and preregistered decision
  rules, backed by ~1,794 automated tests including deliberate
  leakage-failure cases.
* Applied preregistered stopping rules to conclude a negative result
  honestly: documented that no candidate met its promotion criteria,
  preserved the held-out final test unopened, and shipped a full evidence
  ledger tracing every reported figure to its source artifact.

## Interview answer: why is this valuable if the models did not beat persistence?

Three reasons.

**It found out which plausible ideas fail, and why.** "Commodity prices
should predict factory stress" is a reasonable hypothesis that a lot of
people would assume works. This project tested it under realistic data
availability and found it did not help - and diagnosed the reasons
structurally, not just statistically. Half the commodity features turned
out to be constant for half the industries because the official
input-output table assigns them a zero coefficient. Per-industry scaling
of one national price series adds no new temporal information at all,
which I proved with rank arithmetic before running any model. Those are
findings about the data, and they would apply to anyone else attempting
the same thing.

**It did not spend the final test.** The easiest way to manufacture a
positive result would have been to keep trying specifications until one
cleared the bar. I set the stopping rules in advance, hit them, and
stopped. The held-out data is still untouched and still meaningful,
which means a future attempt with genuinely better inputs can still get
an honest read from it. A number obtained by peeking would have been
worth less than nothing.

**The infrastructure is the durable part.** Getting publication timing
right was the hardest engineering problem here, and fixing it made the
baselines measurably worse - which was the correct direction, because it
removed information nobody actually had. The timing contracts, the
lineage and checksum discipline, the walk-forward harness and the test
suite all survive the negative result and would be the starting point for
any next attempt.

A study that reports what did not work, with the evidence to show it was
tested properly, is more useful than one that reports a number nobody can
reproduce.

