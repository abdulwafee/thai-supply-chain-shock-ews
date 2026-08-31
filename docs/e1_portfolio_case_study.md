# Can Commodity Prices Warn You About Factory Slowdowns?

*A forecasting study on Thai manufacturing - and an honest negative result.*

## The question

When oil, metal or rubber prices move, factories feel it. If that shows
up in production data a month or two later, a forecaster could see
trouble coming.

I built a system to test that idea on twelve Thai manufacturing
industries, forecasting a monthly stress score one and three months
ahead. The honest answer, after building the whole pipeline: **the
commodity signals did not improve on a simple forecast that just assumes
next month looks like last month.**

This write-up is about how I got to that answer, and why the way I got
there matters more than the answer itself.

## Why you cannot just shuffle the data

The instinct with any dataset is to split it randomly: 80% to train, 20%
to test. For a time series that quietly cheats, in two ways.

**The obvious way:** a random split lets the model learn from March to
predict February. It sees the future.

**The subtle way, which cost me most of the project:** even a correct
chronological split can cheat if you ignore *when data was published*.
The production index for March is not available in March. It is published
weeks later. If you build a March forecast using March's index because
your table has a March row, you have used a number nobody had yet. The
table gives no hint that anything is wrong - the column is right there,
full of plausible values.

So the whole system is organised around a single question asked at every
step: *what did somebody actually know on the day this forecast was
made?* Every forecast is stamped with an issue month, and every input has
to prove it was published by then.

## Getting the timing right

Two different problems, two different solutions.

For commodity prices I found the **archived original releases** - the
monthly price bulletins as first published, not the revised figures you
get today. Revised data is a subtle form of hindsight: it tells you what
the price turned out to be, not what a forecaster would have seen. I
verified publication dates against the archive so each price could be
matched to the first forecast that could legitimately have used it.

For Thai refinery prices no such archive of original releases exists. I
could only get today's version of historical documents. Rather than
pretend otherwise, I recorded the timing as a **conservative assumption**
- assume the data was two months late - and labelled it an assumption
everywhere it appears, so nobody downstream mistakes it for a measurement.

The production target itself has no archived versions at all. That is a
real limitation and it is stated in every report: this study is
release-aware, but it is not a point-in-time reconstruction of the past.

## Connecting prices to industries

A rubber price should matter more to a tyre maker than to an electronics
assembler. To make that concrete rather than hand-wavy, I used the
national statistics office's **input-output table** - an official matrix
of how much each industry buys from every other sector.

That gives a per-industry exposure number for each commodity, straight
from official accounts rather than from my own guesswork. It is
attribution, not causation: it says an industry buys from a sector, not
that a price move flows through to its output.

## The most interesting thing I found (before any model ran)

Two structural discoveries changed the project, and both came from
auditing the design rather than from a result.

**Half the commodity features were constant.** For six of the twelve
industries, the official table gives a *zero* coefficient on the mapped
commodity sectors. Multiply a moving price by zero and you get a column
that never changes - a predictor that cannot predict. Those industries'
forecasts were just the benchmark, wearing a model's clothes. Finding
this before reading any outcome is the difference between reporting a
result and understanding one.

**Per-industry scaling adds nothing over time.** For the refinery-price
work, I multiplied one national price series by each industry's exposure.
It looks like eleven industry histories. It is one history times eleven
constants. I proved this with rank arithmetic - the eleven rows at any
month collapse to a single direction - and, importantly, proved it
*without looking at any outcome*. That result reshaped the model design:
if scaling adds no new temporal information, the only architecture that
can use exposure meaningfully is one that pools industries and lets
exposure modulate a shared effect.

## Rebuilding the benchmark honestly

Partway through, I realised my first evaluation had the publication
timing wrong. Fixing it made every benchmark *worse* - the naive forecast
went from about 14.5 to about 17.1 average error, because it was now
restricted to genuinely available data.

That was the right direction. A benchmark that looks too good usually
means it is seeing something it should not. I rebuilt the baselines under
the corrected timing rules and registered them as the reference point,
then re-ran everything against them.

I also want to be precise about what the reference is: the persistence
forecast was **selected** under a rule fixed in advance, and its
comparison against the next-best alternative was statistically
inconclusive. It is the registered reference, not a demonstrated champion.

## What the experiments found

Three candidate models, all evaluated on fifteen monthly forecast dates.
Lower error is better; the reference is the persistence forecast.

| candidate | horizon | model error | reference error | verdict |
| --- | ---: | ---: | ---: | --- |
| commodity model | 1 month | 17.56 | 17.09 | no improvement |
| commodity model | 3 months | 17.91 | 16.63 | no improvement |
| refinery-price model | 1 month | 17.11-17.17 | 17.09 | inconclusive |
| refinery-price model | 3 months | 18.21-18.21 | 16.63 | inconclusive |

No candidate had a lower error than the reference. Every uncertainty
interval included zero, which on fifteen data points is what an honest
test usually produces. And for the refinery-price model, a safety check
mattered more than the average error: it **missed more high-stress months**
than the plain forecast did. For an early-warning system, missing the
warnings is the failure that counts.

I want to be careful about what this does and does not show. It shows
these signals did not help, in this setup, with this much data. It does
**not** show that commodity prices are unrelated to industrial stress -
fifteen months cannot settle that, and I did not try to.

## Why leaving the final test unopened is the good outcome

At the start I set aside the most recent months as a final test and wrote
down the rule: a model may only be evaluated on it after clearing agreed
thresholds on the development data first.

No model cleared them. So the final test was never opened.

It would have been easy to peek. Try another regularisation strength,
another model family, drop the industries that were dragging the average
down, keep the fuel oil that scored slightly better. Any of those might
have produced a number worth writing up - and all of them would have been
fitting the answer rather than testing it. Each attempt spends a little
of the final test's credibility, and there is no way to earn it back.

The set-aside data is still untouched. If someone brings genuinely new
evidence later - better industry-level fuel consumption data, a newer
input-output table, real publication dates - the test is still there and
still means something. That is the result I am most confident about.

## What I built

* An ingestion pipeline for four official statistical sources, with
  checksums, retrieval manifests and recorded provenance for every file.
* Publication-timing logic that keeps each forecast to what was knowable
  on its own issue date, with automated guards that fail loudly rather
  than silently.
* Industry exposure matrices derived from official input-output accounts,
  with the aggregation verified two independent ways.
* A walk-forward evaluation harness with clustered bootstrap uncertainty
  and preregistered decision rules.
* Around 1,700 automated tests, including deliberately constructed
  failure cases: every leakage rule has a test that breaks it on purpose
  and requires the guard to catch it.
* Content checksums and lineage records so every number in the final
  report can be traced to the artifact that produced it.

## Skills this demonstrates

Time-series forecasting design; data-leakage prevention; point-in-time
and vintage data handling; working with official statistical sources and
input-output economics; regularised regression and residual modelling;
bootstrap uncertainty with clustered dependence; preregistration and
stopping rules; reproducible pipelines with checksums and lineage;
large-scale automated testing; and technical writing that distinguishes
what was shown from what was assumed.

## What would restart this project

Not another model. The pipeline is built and the data is exhausted for
now; a different regression on the same evidence would only be a new way
of asking a question already answered.

What would restart it: industry-level fuel consumption statistics
specific enough to replace a broad proxy; a newer input-output table
materially changing the exposure structure; verified historical
publication dates that firm up the timing assumptions; or simply more
history, which is the one thing that would narrow the uncertainty
intervals that made these results inconclusive rather than decisive.

---

*Everything above is reproducible: the full technical closeout, the
evidence ledger with a pointer for every number, and the task-level
artifact index are in this repository.*

