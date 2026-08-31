# Task C11-R1 - Specification-Correction and Outcome-Access Governance

*Generated 2026-08-30T01:52:51.925379+00:00. Config `fuel_oil_architecture_governance_v1`.*

**Supersedes the STATUS of `C11`. Supersedes its findings: `none`.**

C11-R1 corrects how the C11 architecture decision is formally described.
It changes none of its mathematics, and it removes none of its
disclosures. Two facts that C11 reported together are separated here and
stay separated:

1. **The decision is dependency-clean** - it reproduces exactly without
   any D-series result.
2. **The original execution was not outcome-blind** - a development
   metric artifact was opened during it.

No umbrella `outcome_free: true` is claimed anywhere.

## The corrected decision status

| field | value |
| --- | --- |
| `architecture_decision_status` | `exploratory_supported_after_documented_specification_correction` |
| `architecture_mathematically_supported` | `True` |
| `architecture_confirmatorily_selected` | `False` |
| `architecture_selection_outcome_independence_proven_by_dependency` | `True` |
| `original_process_outcome_blind` | `False` |
| `eligible_for_confirmatory_claims` | `False` |
| `eligible_for_locked_test` | `False` |
| `architecture_invalidated_by_process_imperfection` | `False` |
| `architecture_upgraded_because_the_correction_is_convincing` | `False` |

## 1. The preserved C11 record

C11's durable checksums are unchanged: `True`. Byte-identical: `True`. Artifacts edited: `none`.

| artifact | byte sha256 | carries a timestamp |
| --- | --- | --- |
| `docs/c11_architecture_decision.json` | `d482d80fa74f5a488d3b02f4a2fd0a38d0155b9393f43c779c63cb6345cd3d73` | `True` |
| `docs/c11_architecture_decision.md` | `9a5467c89243f0c3b6aa79075814abd13ceb6b4e77fbf4b0f9c4cbb68124046e` | `True` |
| `docs/c11_architecture_decision_protocol.md` | `e823f9dcc1e7ce6dd7cd242e7e8f957d868b7a0d7c44ba4398eca96def31cd3d` | `False` |
| `configs/fuel_oil_modeling_architecture.yaml` | `b90229da37d9393b646746d7bd2a5889df5903f9f81d961aa765a9cdbfde348d` | `False` |

| durable checksum | value |
| --- | --- |
| `c11_content_checksum` | `6d525648f0e7e30860dc065c17a896426a0cf008f7ef62096974d4954c9f6d77` |
| `c11_decision_checksum` | `001b1d901311c1da0de1e707ca10a97f91e54584b21e52ee8c943421fc068403` |
| `c11_decision_criteria_checksum` | `0f81513566f98d1d5047dcb298935607f5abdb35510cf0e3c53c1bc6998d8397` |
| `c11_lineage_checksum` | `73a3b1e6f680e2ea2be1f9f50d5fbcb7b21e53d0064dcfee222c725b49e33a4b` |

A **byte digest** is a forward integrity baseline only: the Markdown and
JSON carry a generation timestamp, so a legitimate rerun moves them. The
**content checksum** excludes timestamps and is the durable identity, so
a change there would mean the record itself changed. C11 was not edited;
this document is a sidecar, because a correction written into a generated
file is erased by the next regeneration.

Preserved disclosures: `original_gate_expectation`, `original_observed_gate_result`, `gate_correction_disclosure`, `d3_result_file_access_disclosure`.

## 2. The original gate and the corrected gate, kept apart

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

**Gate:** `pooled_interaction_survives_the_specified_preprocessing`

### What was preregistered

> Per-industry standardization would reduce the STACKED combined rank from 10 to 5.

As implemented: The gate required the per-industry-standardisation COUNTERFACTUAL to show a stacked rank drop, which made a gate about the specified preprocessing depend on a construction the preprocessing contract forbids.

### What was observed

| observation | value |
| --- | --- |
| stacked combined rank under the prohibited preprocessing | **10** |
| centred exposures contain both signs | `True` |
| positive / negative sign industries | 3 / 8 |
| per-industry standardisation maps the interaction to | `+Xtilde or -Xtilde` |
| stacking both sign groups preserves two directions | `True` |

### The correct measurements

| measurement | value |
| --- | --- |
| `within_industry_combined_rank` | `5` |
| `intended_combined_rank` | `10` |
| `interaction_blocks_intended` | `11` |
| `interaction_blocks_after_prohibited_preprocessing` | `2` |
| `sign_equivalence_groups` | `2` |
| `sign_identity_residual_approx` | `4.441e-16` |
| `selected_preprocessing_retains_interaction_rank` | `True` |
| `selected_preprocessing_interaction_rank` | `5` |
| `prohibited_preprocessing_destroys_continuous_exposure_magnitude` | `True` |
| `prohibited_preprocessing_destroys_magnitude_even_though_stacked_rank_is_10` | `True` |

### Why the correction is justified

**Incorrect measurement.** Does the prohibited preprocessing force the entire STACKED matrix rank to five? This is FALSE, because the exposure signs preserve two stacked directions.

**Correct measurement.** Does per-industry standardization preserve continuous exposure MAGNITUDE within an industry? This is FALSE: standardize(E_g X) equals standardize(X) when E_g > 0 and -standardize(X) when E_g < 0, so only the sign survives and the magnitude does not.

> The corrected gate is valid on mathematical grounds, but it remains a post-observation specification correction. Reproducibility does not convert it into preregistration.

The original gate asked whether the prohibited preprocessing forces the entire stacked matrix to rank five. It does not, because the centred exposures carry both signs and +Xtilde and -Xtilde span two directions. The question the gate should have asked is whether per-industry standardisation preserves continuous exposure magnitude within an industry. It does not: standardize(E_g X) equals standardize(X) when E_g is positive and -standardize(X) when it is negative, so only the sign survives. No tolerance and no threshold moved; the gate was measuring the wrong quantity, and the quantity was corrected after the result was visible.

Corrected gate: Under THE SPECIFIED preprocessing the interaction block is present at its expected rank, the combined rank equals the sum of the two block ranks, the interaction is not standardised inside an industry, and a constant exposure would be detected as a rank-zero interaction.

Frozen correction checksum `99ce567841cf79b457572d4db5fff71cd9438622994ad05b5f30f076092545e7`.

## 3. The outcome-access incident

During C11 a development metric artifact was opened. The benchmark contract name it was opened for was already available in non-result documentation, so the file was not required. No metric value entered the C11 configuration, the candidate matrices, any checksum, the gate arithmetic or the architecture selection, and the decision reproduces exactly without it. A guard added afterwards prevents recurrence. It does not alter what happened, and a clean rerun does not restore an outcome-blind execution history.

**6** D-series JSON documents were opened during C11; **1** had metric values displayed.

| file | metric values present | metric values displayed | required |
| --- | --- | --- | --- |
| `docs/d3_operational_baseline_results.json` | `True` | `True` | `False` |
| `docs/d4_operational_model_results.json` | `True` | `False` | `False` |
| `docs/d3_locked_test_manifest.json` | `False` | `False` | `False` |
| `docs/d3_restored_d1_checksums.json` | `False` | `False` | `False` |
| `docs/d3r1_artifact_inventory.json` | `False` | `False` | `False` |
| `docs/d3r1_benchmark_interpretation.json` | `False` | `False` | `False` |

| field | value |
| --- | --- |
| `development_metric_artifact_accessed` | `True` |
| `development_target_values_accessed` | `False` |
| `locked_test_accessed` | `False` |
| `metric_values_used_in_architecture_decision` | `False` |
| `metric_artifact_required_for_decision` | `False` |
| `outcome_free_execution` | `False` |
| `decision_reproducible_without_metric_artifact` | `True` |
| `later_guard_retroactively_erases_access` | `False` |
| `clean_rerun_restores_original_outcome_blindness` | `False` |
| `locked_test_manifest_opened` | `True` |
| `locked_test_outcomes_accessed` | `False` |
| `umbrella_outcome_free_claim_made` | `False` |

> No target table, target column or target observation was opened. The D-series files above are audit documents; the target tables (targets/industry_month_targets, production_stress_month, forecast_target_raw) were never opened during C11, which is independently supported by the static read-call inspection of the C11 runner and by the absence of any target path in this session's C11 commands.

> A guard added afterwards prevents recurrence. It does not, and is not claimed to, alter what happened.

## 4. Information-flow audit

`architecture_decision_dependency_clean`: **True**

| instrument | result |
| --- | --- |
| inputs opened (allowlist admitted) | 5 |
| D-series paths opened | **0** |
| read call sites statically inspected | 24 |
| read calls opening a forbidden path | **0** |
| offending imports | `none` |
| metric-substitution invariance | `True` |

Fabricated metric keys injected into an isolated fixture: `channel_performance_fo1500`, `channel_performance_fo600`, `high_stress_outcome_rate`, `macro_industry_mae`, `rmse`. Written to disk: `False`. The selected architecture did not move.

Permitted inputs are admitted by **name**, not by failing to match a
forbidden pattern - a denylist admits every artifact nobody anticipated,
which is how the original access happened.

**This proves:** The architecture reproduces exactly from C9/C10 structural artifacts, the sector-093 exposure vector, the candidate-design formulas and the frozen preprocessing rules, with no D-series path opened and no metric value reachable.

**This does not prove:** That the original C11 execution was outcome-blind. A development metric artifact was opened during it, and no dependency argument changes that.

## 5. Reproduction without any D-series access

All reproduced: **True** (33 checks). Architecture: `pooled_common_effect_plus_centered_sector093_interaction`.

| variant | source | interaction | combined | full / cols | const-exp | invalid coding | B projector |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fo1500_direct_sector093` | 5 | 5 | 10 | 21 / 21 | 0 | 21 / 22 | 1.110e-15 |
| `fo600_direct_sector093` | 5 | 5 | 10 | 21 / 21 | 0 | 21 / 22 | 8.882e-16 |

| variant | within-industry rank | stacked rank | interaction blocks | sign residual |
| --- | ---: | ---: | ---: | ---: |
| `fo1500_direct_sector093` | **5** | 10 | **11 -> 2** | 4.441e-16 |
| `fo600_direct_sector093` | **5** | 10 | **11 -> 2** | 4.441e-16 |

## 6. Architecture scope, preserved

`r[g,t,h] = alpha[g,h] + sum_f beta[h,f] * xtilde[t,f] + sum_f theta[h,f] * ec[g] * xtilde[t,f]`

| field | value |
| --- | --- |
| `source_transformations_scaled_across_training_issue_months` | `True` |
| `frozen_centered_sector093_exposure` | `True` |
| `interaction_constructed_after_source_scaling` | `True` |
| `per_industry_interaction_standardization` | `False` |
| `industry_fixed_effects_without_redundant_global_intercept` | `True` |
| `horizons_fitted_separately` | `True` |
| `ind_04_benchmark_passthrough` | `True` |
| `fo600_and_fo1500_separate_variants` | `True` |
| `simultaneous_channel_entry` | `False` |
| `outcome_based_channel_promotion` | `False` |
| `interpretation` | `non_causal_predictive_interaction` |

## 7. Closure gates

| gate | passed |
| --- | --- |
| `c11_original_record_preserved` | `True` |
| `original_and_corrected_gate_sets_kept_separate` | `True` |
| `correction_not_presented_as_preregistered` | `True` |
| `outcome_access_incident_recorded_accurately` | `True` |
| `architecture_reproduced_without_d_series_access` | `True` |
| `architecture_decision_dependency_clean` | `True` |
| `decision_status_is_exploratory_not_confirmatory` | `True` |
| `architecture_scope_preserved` | `True` |
| `no_model_prediction_target_or_metric_artifact_created` | `True` |

All closure gates passed: **True**.

## 8. Bounded D5 authorization

> All nine closure gates passed. D5 is authorized as a development-only exploratory evaluation of the Candidate-C pooled architecture, with both fuel-oil variants kept as separate parallel variants. Channel selection, purge metrics, confirmatory claims and the locked test remain unauthorized.

| field | value |
| --- | --- |
| `d5_protocol_preregistration_authorized` | `True` |
| `d5_development_target_join_authorized` | `True` |
| `d5_exploratory_modeling_authorized` | `True` |
| `d5_channel_selection_authorized` | `False` |
| `d5_confirmatory_claims_authorized` | `False` |
| `d5_purge_evaluation_authorized` | `False` |
| `d5_locked_test_evaluation_authorized` | `False` |

### Scope of the grant

| field | value |
| --- | --- |
| `development_issue_months` | `['2024-01', '2025-03']` |
| `operational_release_timing_contract` | `operational_contract_v1` |
| `variants_evaluated` | `['fo600_direct_sector093', 'fo1500_direct_sector093']` |
| `variants_are_separate_parallel_exploratory` | `True` |
| `combined_or_selected_fuel_oil_channel` | `False` |
| `architecture` | `C_pooled_common_effect_plus_centered_exposure_interaction` |
| `other_architectures_authorized` | `False` |
| `ind_04_in_evaluation_denominators` | `True` |
| `ind_04_benchmark_passthrough` | `True` |
| `validation_and_uncertainty_clustered_by` | `issue_month` |
| `operational_benchmarks_reproduced_from_registered_formulas` | `True` |
| `purge_metrics` | `False` |
| `locked_test_access` | `False` |
| `confirmatory_claims` | `False` |
| `model_feature_approval_from_development_evidence_alone` | `False` |

The authorization is void if the dependency-clean reconstruction fails: `True`.

## Checksums

Correction `99ce567841cf79b457572d4db5fff71cd9438622994ad05b5f30f076092545e7`. Information flow `97a3edd74ab196d0e6e2a21f197fa5cbf863dff251a1eb2157db16dc534394ee`. Governance `81f18e8ad449283105ca6e0e8e6324280a4aaa4c6684e0f69635945c1c3a1851`. Content `a536dbb85444add1051e589e170bcc10756ff335ba1283723ac1644b4d36dbca`.

