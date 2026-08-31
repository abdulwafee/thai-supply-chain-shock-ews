# Erratum - Task C11 Architecture Decision

**Status:** active correction to the *methodological status* claimed in
C11 reporting. **Raised and closed by:** Task C11-R1.
**Applies to:** [`c11_architecture_decision.md`](c11_architecture_decision.md)
and [`c11_architecture_decision_protocol.md`](c11_architecture_decision_protocol.md).

This erratum is a **sidecar**. The correction lives here instead of being
edited into the generated C11 documents - otherwise a later regeneration
would silently erase it, and the record of what C11 actually claimed
would be lost. The C11 files are unchanged and their digests are pinned
in [`c11r1_governance_decision.json`](c11r1_governance_decision.json).

**C11's mathematics is not corrected here.** Every rank, residual and
identity it reported reproduces exactly, without opening any D-series
file. What is corrected is how the decision may be described.

---

## 1. One of the nine gates did not pass as preregistered

C11 reported that all nine mandatory gates passed. That is true of the
**corrected** gate set, not of the **originally preregistered** one.

The gate `pooled_interaction_survives_the_specified_preprocessing` was preregistered as:

> Per-industry standardization would reduce the STACKED combined rank from 10 to 5.

The observed stacked rank was **10**, not 5. So the original gate, as implemented, **did not pass**.

| field | value |
| --- | --- |
| `original_preregistered_stacked_rank_expectation` | `5` |
| `observed_stacked_rank_under_prohibited_preprocessing` | `10` |
| `original_gate_implementation_valid` | `False` |
| `original_preregistered_gate_set_passed` | `False` |
| `gate_implementation_corrected_after_observation` | `True` |
| `corrected_gate_set_passed` | `True` |
| `thresholds_changed_after_observation` | `False` |
| `expectations_rewritten_as_preregistered` | `False` |
| `architecture_decision_cleanly_preregistered` | `False` |

## 2. The correction is a change of quantity, not of tolerance

No tolerance and no threshold moved. The rank tolerance, the
duplicate-column tolerance and every residual tolerance stand exactly as
preregistered. The gate was measuring the wrong quantity.

**Incorrect question.** Does the prohibited preprocessing force the entire STACKED matrix rank to five? This is FALSE, because the exposure signs preserve two stacked directions.

**Correct question.** Does per-industry standardization preserve continuous exposure MAGNITUDE within an industry? This is FALSE: standardize(E_g X) equals standardize(X) when E_g > 0 and -standardize(X) when E_g < 0, so only the sign survives and the magnitude does not.

The collapse C11 claimed is real; it simply is not visible in the stacked
rank. Within an industry the combined block falls to rank
**5**, and
**11** distinct
exposure-proportional interaction blocks collapse to
**2** sign groups.

> The corrected gate is valid on mathematical grounds, but it remains a post-observation specification correction. Reproducibility does not convert it into preregistration.

## 3. The execution was not outcome-blind

**6** D-series JSON documents were opened
during C11 and **1** had
development metric values displayed. The file was not required: the
benchmark contract name was already present in non-result documentation.

No metric value entered the C11 configuration, the candidate matrices, any
checksum, the gate arithmetic or the architecture selection, and C11-R1
reproduces the decision without opening any of them. That makes the
decision **dependency-clean**. It does not make the execution history
outcome-blind, and a guard added afterwards does not reach backwards.

## 4. The resulting status

`architecture_decision_status`: **exploratory_supported_after_documented_specification_correction**

The architecture is *mathematically supported* and *not confirmatory*. An
imperfect process does not invalidate a reproduced identity, and a
convincing correction does not upgrade an exploratory selection.

Full record: [`c11r1_governance_decision.md`](c11r1_governance_decision.md).

