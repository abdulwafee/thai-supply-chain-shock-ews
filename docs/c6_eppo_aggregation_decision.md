# Task C6 - Monthly Aggregation Decision

**No production monthly table is created in C6.** This preregisters the
aggregation contract a later task may use, chosen from source semantics
and archive evidence only.

* `production_table_created_in_c6`: `False`
* `selected_from_predictive_performance`: `False`

## Candidate rules

| rule | description | daily completeness |
| --- | --- | --- |
| `arithmetic_mean_of_verified_daily` | arithmetic mean of all verified daily effective observations | high |
| `last_verified_effective_in_month` | last verified effective observation in the reference month | low |
| `duration_weighted_effective` | duration-weighted price, valid only if a price is proven effective until superseded | n/a |

## Operational boundary

* default reference month: **`completed_t_minus_1`**
* same-month partial aggregation permitted: `False`
* observations after the issue date permitted: `False`

At operational issue month *t* the completed reference month is *t-1*. A
partial month *t* is not aggregated, because part of it lies after the
issue date and would leak.

## Why no rule is approved yet

`monthly_aggregation_contract_approved: false`. Point-in-time status is
`not_supported` (0/254 observations evidenced),
so no aggregation of these values can be described as availability-safe yet.
Approving a rule now would fix a contract on top of unverified timing.
