"""Task C4 — industry-conditioned commodity feature matrix.

Contract tests confirm the matrix is what C4 promised. Synthetic failure tests
confirm each guard fires — a rule that has never rejected anything is an
assumption, not a safeguard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.features import commodity_features as CF  # noqa: E402
from thai_supply_chain_ews.features import conditioned_availability as CA  # noqa: E402
from thai_supply_chain_ews.features import conditioned_lineage as CL  # noqa: E402
from thai_supply_chain_ews.features import feature_snapshots as FS  # noqa: E402
from thai_supply_chain_ews.features import industry_conditioning as IC  # noqa: E402
from thai_supply_chain_ews.features.feature_availability import (  # noqa: E402
    PRIMARY_POLICY,
    SENSITIVITY_POLICY,
)

CONFIG = yaml.safe_load(
    (ROOT / "configs" / "industry_conditioned_features.yaml").read_text(encoding="utf-8")
)
SCHEMA = yaml.safe_load(
    (ROOT / "schemas" / "industry_conditioned_feature.schema.yaml").read_text(encoding="utf-8")
)
AUDIT_JSON = ROOT / "docs" / "c4_industry_conditioned_feature_audit.json"
C3_MATRIX = ROOT / "docs" / "c3_commodity_exposure_matrix.json"
C1_5_AUDIT = ROOT / "docs" / "c1_5_commodity_timing_audit.json"


@pytest.fixture(scope="module")
def audit():
    return json.loads(AUDIT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def c3():
    return json.loads(C3_MATRIX.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def c2_rows():
    loaded = CF.load_first_release_observations(C1_5_AUDIT)
    return {
        PRIMARY_POLICY.name: CF.build_feature_table(
            loaded["observations"], loaded["required_months"], PRIMARY_POLICY
        ),
        SENSITIVITY_POLICY.name: CF.build_feature_table(
            loaded["observations"], loaded["required_months"], SENSITIVITY_POLICY
        ),
    }


@pytest.fixture(scope="module")
def availability():
    spec = CONFIG["structural_availability"]
    return CA.StructuralAvailability(
        structural_reference_year=str(spec["structural_reference_year"]),
        structural_available_by=str(spec["structural_available_by"]),
        evidence_type=spec["evidence_type"],
        evidence_url=spec["evidence_url"],
        document_date=str(spec["document_date"]),
        publication_date=str(spec["publication_date"]),
        evidence_checksum="fixture",
        status=spec["status"],
        byte_identity_verified_at_that_date=False,
    )


@pytest.fixture(scope="module")
def rows(c2_rows, c3, availability):
    return IC.build_conditioned_matrix(
        c2_rows, c3["canonical_rows"], availability, c3["io_source"]["sha256"]
    )


# --- input invariants ---------------------------------------------------------


def test_c2_input_invariants(c2_rows):
    for policy, table in c2_rows.items():
        assert len(table) == 1224, policy
        assert {r["availability_policy"] for r in table} == {policy}
        assert {r["source_value_type"] for r in table} == {"archived_first_release"}
    primary = c2_rows[PRIMARY_POLICY.name]
    assert len({r["series_id"] for r in primary}) == 4
    assert len({r["feature_name"] for r in primary}) == 5
    for series in {r["series_id"] for r in primary}:
        assert sum(1 for r in primary if r["series_id"] == series) == 306
    assert PRIMARY_POLICY.name == "operational_lag_2m"
    assert SENSITIVITY_POLICY.name == "publication_lag_1m"


def test_c3_input_invariants(c3):
    pairs = c3["canonical_rows"]
    assert len(pairs) == 48
    assert len({r["industry_id"] for r in pairs}) == 12
    assert len({r["commodity_series_id"] for r in pairs}) == 4
    assert sum(1 for r in pairs if r["industry_pair_feature_eligible"]) == 43
    assert sum(1 for r in pairs if not r["industry_pair_feature_eligible"]) == 5
    assert sum(1 for r in pairs if r["direction_channel"] == "mixed_or_ambiguous") == 3
    assert sum(
        1 for r in pairs
        if r["commodity_proxy_fit_status"] == "not_fit_for_commodity_specific_use"
    ) == 2
    assert sum(1 for r in pairs if r["shared_io_source_sector"]) == 24


def test_exact_five_excluded_pairs(c3, rows):
    excluded = {
        (r["industry_id"], r["commodity_series_id"])
        for r in c3["canonical_rows"] if not r["industry_pair_feature_eligible"]
    }
    assert excluded == {
        ("IND-12", "aluminum_usd_mt"), ("IND-12", "copper_usd_mt"),
        ("IND-06", "rubber_rss3_usd_kg"), ("IND-08", "aluminum_usd_mt"),
        ("IND-08", "copper_usd_mt"),
    }
    generated = {(r["industry_id"], r["commodity_series_id"]) for r in rows}
    assert not (generated & excluded)
    assert len(generated) == 43


def test_ineligible_coefficients_retained_in_the_exclusion_audit(audit):
    excluded = audit["excluded_pairs"]
    assert len(excluded) == 5
    reasons = {e["exclusion_reason"] for e in excluded}
    assert reasons == {"commodity_proxy_fitness", "mixed_or_ambiguous_direction"}
    for entry in excluded:
        assert entry["direct_exposure_retained"] is not None
        assert entry["total_requirement_exposure_retained"] is not None
        assert entry["converted_to_zero"] is False
        assert entry["conditioned_features_generated"] == 0
    proxy = [e for e in excluded if e["exclusion_reason"] == "commodity_proxy_fitness"]
    assert {e["industry_id"] for e in proxy} == {"IND-12"}
    assert all(e["direct_exposure_retained"] > 0 for e in proxy)


# --- structural availability --------------------------------------------------


def test_reference_year_is_not_treated_as_publication_date(availability, audit):
    assert availability.structural_reference_year == "2015"
    assert availability.structural_available_by == "2020-03-31"
    assert availability.status == "verified_before_development"
    record = audit["structural_availability"]
    assert record["reference_year_treated_as_publication_date"] is False
    assert record["download_timestamp_used_as_availability"] is False
    assert record["evidence_type"] == "official_download_page_publication_date"
    assert record["byte_identity_verified_at_that_date"] is False
    assert record["fully_real_time"] is False


def test_backdating_to_the_reference_year_is_rejected():
    """Synthetic: a 2015 availability date would leak years of structure."""
    with pytest.raises(CA.StructuralAvailabilityError, match="reference year"):
        CA.StructuralAvailability(
            structural_reference_year="2015", structural_available_by="2015-01-01",
            evidence_type="x", evidence_url="u", document_date=None,
            publication_date=None, evidence_checksum="c",
            status="verified_before_development",
            byte_identity_verified_at_that_date=False,
        )


def test_structure_published_after_a_forecast_origin_is_rejected():
    """Synthetic: a late structural source must block the primary matrix."""
    late = CA.StructuralAvailability(
        structural_reference_year="2015", structural_available_by="2024-06-30",
        evidence_type="x", evidence_url="u", document_date=None,
        publication_date=None, evidence_checksum="c",
        status="verified_after_development_start",
        byte_identity_verified_at_that_date=False,
    )
    assert late.supports_origin("2024-01-01") is False
    with pytest.raises(CA.StructuralAvailabilityError, match="may not proceed"):
        late.assert_supports_primary("2024-01-01")


def test_unresolved_availability_blocks_the_primary_matrix():
    unresolved = CA.StructuralAvailability(
        structural_reference_year="2015", structural_available_by="2020-03-31",
        evidence_type="x", evidence_url="u", document_date=None,
        publication_date=None, evidence_checksum="c", status="unresolved",
        byte_identity_verified_at_that_date=False,
    )
    with pytest.raises(CA.StructuralAvailabilityError, match="unresolved"):
        unresolved.assert_supports_primary("2024-01-01")


def test_availability_is_the_max_of_both_inputs(rows, availability):
    for row in rows:
        assert row["conditioned_available_month"] >= row["base_feature_available_month"]
        assert row["conditioned_available_month"][:7] >= (
            availability.structural_available_by[:7]
        )
        assert row["conditioned_available_month"] == max(
            row["base_feature_available_month"],
            availability.structural_available_by[:7] + "-01",
        )
        assert row["conditioned_available_month"] > row["reference_month"]


def test_future_dated_input_is_rejected():
    with pytest.raises(CA.FutureDatedInputError, match="not after reference month"):
        CA.assert_not_future_dated("2024-06-01", "2024-06-01", "fixture")
    with pytest.raises(CA.FutureDatedInputError):
        CA.assert_not_future_dated("2024-06-01", "2024-05-01", "fixture")


# --- variants -----------------------------------------------------------------


def test_exactly_three_variants_each_varying_one_assumption():
    assert len(IC.MATRIX_VARIANTS) == 3
    names = [v.name for v in IC.MATRIX_VARIANTS]
    assert names == [
        "primary_direct_lag2", "timing_sensitivity_direct_lag1",
        "structural_sensitivity_total_lag2",
    ]
    primary = IC.MATRIX_VARIANTS[0]
    assert primary.is_primary and primary.label == "primary"
    assert primary.availability_policy == "operational_lag_2m"
    assert primary.exposure_field == "direct_exposure"
    for variant in IC.MATRIX_VARIANTS[1:]:
        assert variant.is_primary is False
        assert variant.label == "sensitivity_only"
        varied = int(variant.availability_policy != "operational_lag_2m") + int(
            variant.exposure_field != "direct_exposure"
        )
        assert varied == 1, variant.name


def test_no_combined_double_sensitivity_variant(audit):
    assert audit["combined_double_sensitivity_variant_created"] is False
    assert CONFIG["combined_double_sensitivity_variant_created"] is False
    with pytest.raises(IC.ConditioningError, match="varies 2 assumptions"):
        IC.MatrixVariant(
            name="lag1_total", availability_policy="publication_lag_1m",
            exposure_field="total_requirement_exposure", is_primary=False,
            label="sensitivity_only", varies_from_primary="both",
        )


def test_lag_one_table_cannot_be_marked_primary():
    """Synthetic: a sensitivity table presented as primary must be refused."""
    with pytest.raises(IC.ConditioningError, match="must use operational_lag_2m"):
        IC.MatrixVariant(
            name="disguised", availability_policy="publication_lag_1m",
            exposure_field="direct_exposure", is_primary=True, label="primary",
            varies_from_primary="none",
        )
    with pytest.raises(IC.ConditioningError, match="both primary and sensitivity"):
        IC.MatrixVariant(
            name="both", availability_policy="operational_lag_2m",
            exposure_field="direct_exposure", is_primary=True,
            label="sensitivity_only", varies_from_primary="none",
        )


def test_direct_is_primary_and_total_is_sensitivity_only(rows):
    primary = [r for r in rows if r["matrix_variant"] == "primary_direct_lag2"]
    assert {r["exposure_variant"] for r in primary} == {"direct_exposure"}
    assert {r["availability_policy"] for r in primary} == {"operational_lag_2m"}
    assert all(r["is_primary"] for r in primary)

    structural = [
        r for r in rows if r["matrix_variant"] == "structural_sensitivity_total_lag2"
    ]
    assert {r["exposure_variant"] for r in structural} == {"total_requirement_exposure"}
    assert not any(r["is_primary"] for r in structural)

    timing = [r for r in rows if r["matrix_variant"] == "timing_sensitivity_direct_lag1"]
    assert {r["availability_policy"] for r in timing} == {"publication_lag_1m"}
    assert {r["exposure_variant"] for r in timing} == {"direct_exposure"}
    assert not any(r["is_primary"] for r in timing)
    assert len({r["matrix_variant"] for r in rows if r["is_primary"]}) == 1


def test_variant_may_not_mix_exposure_fields(rows):
    """Synthetic: mixing direct and total inside one variant must be caught."""
    broken = deepcopy(rows)
    for row in broken:
        if row["matrix_variant"] == "primary_direct_lag2":
            row["exposure_variant"] = "total_requirement_exposure"
            break
    with pytest.raises(IC.ConditioningError, match="mixes exposure fields"):
        IC._validate(broken, [None] * 43, [], IC.MATRIX_VARIANTS)


# --- formula and counts -------------------------------------------------------


def test_conditioned_feature_formula(rows):
    checked = 0
    for row in rows:
        expected = (
            row["base_feature_value"] * row["exposure_value"]
            * row["price_increase_to_stress_sign"]
        )
        assert row["conditioned_feature_value"] == pytest.approx(expected, rel=1e-12)
        checked += 1
    assert checked == 39474


def test_exact_row_counts(rows, audit):
    assert len(rows) == 39474
    for variant in IC.MATRIX_VARIANTS:
        assert sum(1 for r in rows if r["matrix_variant"] == variant.name) == 13158
    assert audit["canonical_row_count"] == 39474
    assert audit["expected_canonical_row_count"] == 39474
    assert set(audit["rows_per_variant"].values()) == {13158}
    assert CONFIG["expected_counts"]["rows_per_variant"] == 13158
    assert CONFIG["expected_counts"]["combined_canonical_rows"] == 39474
    # 43 pairs x 306 observations, exactly.
    for variant in IC.MATRIX_VARIANTS:
        subset = [r for r in rows if r["matrix_variant"] == variant.name]
        pairs = {(r["industry_id"], r["commodity_series_id"]) for r in subset}
        assert len(pairs) == 43
        for pair in pairs:
            assert sum(
                1 for r in subset
                if (r["industry_id"], r["commodity_series_id"]) == pair
            ) == 306


def test_unique_canonical_key(rows):
    keys = [
        (r["industry_id"], r["commodity_series_id"], r["base_feature_name"],
         r["reference_month"], r["matrix_variant"])
        for r in rows
    ]
    assert len(set(keys)) == len(keys) == 39474


def test_units_are_named_honestly(rows):
    assert IC.conditioned_unit("percent_log") == (
        "percentage_point_log_change_x_exposure_coefficient"
    )
    assert IC.conditioned_unit("$/bbl") == "$/bbl_x_exposure_coefficient"
    for row in rows:
        unit = row["conditioned_unit"].lower()
        assert "exposure_coefficient" in unit
        for forbidden in ("baht", "usd_cost", "elasticity", "causal", "forecast"):
            assert forbidden not in unit


def test_not_normalized_across_commodities_or_industries(rows, audit):
    assert audit["normalized_across_commodities"] is False
    assert audit["normalized_across_industries"] is False
    primary = [
        r for r in rows
        if r["matrix_variant"] == "primary_direct_lag2"
        and r["base_feature_name"] == "price_level"
        and r["reference_month"] == "2024-01-01"
    ]
    by_industry: dict[str, float] = {}
    for row in primary:
        by_industry[row["industry_id"]] = (
            by_industry.get(row["industry_id"], 0.0) + row["exposure_value"]
        )
    for industry, total in by_industry.items():
        assert abs(total - 1.0) > 1e-6, industry


# --- eligibility and direction ------------------------------------------------


def test_null_sign_never_produces_a_feature(rows):
    for row in rows:
        assert row["price_increase_to_stress_sign"] == 1
        assert row["direction_channel"] == "cost_pressure"


def test_ambiguous_direction_forced_to_plus_one_is_rejected(c2_rows, c3, availability):
    """Synthetic: forcing a mixed pair to +1 must fail, not slip through."""
    tampered = deepcopy(c3["canonical_rows"])
    for row in tampered:
        if row["direction_channel"] == "mixed_or_ambiguous":
            row["price_increase_to_stress_sign"] = 1
            row["industry_pair_feature_eligible"] = True
    with pytest.raises(IC.ConditioningError, match="require cost_pressure"):
        IC.build_conditioned_matrix(
            c2_rows, tampered, availability, c3["io_source"]["sha256"]
        )


def test_eligible_pair_with_null_sign_is_rejected(c2_rows, c3, availability):
    tampered = deepcopy(c3["canonical_rows"])
    for row in tampered:
        if row["industry_pair_feature_eligible"]:
            row["price_increase_to_stress_sign"] = None
            break
    with pytest.raises(IC.AmbiguousDirectionError, match="does not infer"):
        IC.build_conditioned_matrix(
            c2_rows, tampered, availability, c3["io_source"]["sha256"]
        )


def test_ineligible_pair_filled_with_zero_is_rejected(rows, c3):
    """Synthetic: fabricating zero rows for excluded pairs must be caught."""
    excluded = next(
        r for r in c3["canonical_rows"] if not r["industry_pair_feature_eligible"]
    )
    # Take one eligible pair's full 306 primary rows and relabel them to an
    # EXCLUDED pair, zero-filled — the exact fabrication the guard must catch.
    source_pair = ("IND-01", "brent_crude_usd_bbl")
    fabricated = deepcopy([
        r for r in rows
        if r["matrix_variant"] == "primary_direct_lag2"
        and (r["industry_id"], r["commodity_series_id"]) == source_pair
    ])
    assert len(fabricated) == 306
    for row in fabricated:
        row.update(
            industry_id=excluded["industry_id"],
            commodity_series_id=excluded["commodity_series_id"],
            conditioned_feature_value=0.0,
            exposure_value=0.0,
        )
    ineligible = [
        r for r in c3["canonical_rows"] if not r["industry_pair_feature_eligible"]
    ]
    with pytest.raises(IC.IneligiblePairError, match="excluded by"):
        IC._validate(fabricated, [excluded], ineligible, IC.MATRIX_VARIANTS[:1])


def test_target_derived_eligibility_is_impossible(audit):
    """Eligibility comes from C3-R1 evidence; C4 reads no target at all."""
    assert audit["target_association_computed"] is False
    assert audit["feature_selection_using_outcomes"] is False
    assert audit["joined_to_mpi_targets"] is False
    assert audit["locked_test_accessed"] is False
    for name in ("industry_conditioning.py", "conditioned_availability.py",
                 "conditioned_lineage.py", "feature_snapshots.py"):
        source = (ROOT / "src" / "thai_supply_chain_ews" / "features" / name).read_text(
            encoding="utf-8"
        )
        for forbidden in ("thai_supply_chain_ews.targets",
                          "thai_supply_chain_ews.evaluation",
                          "mpi_adverse", "production_stress"):
            assert forbidden not in source, (name, forbidden)


# --- zero vs missing ----------------------------------------------------------


def test_structural_zero_remains_numeric_zero(rows):
    zeros = [r for r in rows if r["zero_reason"] == "zero_due_to_exposure"]
    assert zeros
    for row in zeros:
        assert row["exposure_value"] == 0.0
        assert row["conditioned_feature_value"] == 0.0
        assert row["conditioned_feature_value"] is not None


def test_zero_reasons_are_distinct(rows, audit):
    counts = audit["zero_reason_counts"]
    assert set(counts) <= set(IC.ZERO_REASONS)
    assert counts["zero_due_to_exposure"] > 0
    assert counts["zero_due_to_base_feature"] > 0
    assert counts["not_zero"] > 0
    for row in rows:
        if row["zero_reason"] == "zero_due_to_base_feature":
            assert row["base_feature_value"] == 0.0
            assert row["exposure_value"] != 0.0
        if row["zero_reason"] == "not_zero":
            assert row["conditioned_feature_value"] != 0.0


def test_total_requirement_can_be_nonzero_where_direct_is_zero(rows):
    direct_zero = {
        (r["industry_id"], r["commodity_series_id"])
        for r in rows
        if r["matrix_variant"] == "primary_direct_lag2" and r["exposure_value"] == 0.0
    }
    assert direct_zero
    structural = {
        (r["industry_id"], r["commodity_series_id"])
        for r in rows
        if r["matrix_variant"] == "structural_sensitivity_total_lag2"
        and r["exposure_value"] > 0.0
    }
    assert direct_zero & structural, "indirect exposure should survive a direct zero"


# --- lineage ------------------------------------------------------------------


def test_combined_lineage_is_complete_and_reproducible(rows, c3, audit):
    assert audit["lineage_rows_verified"] == 39474
    checked = 0
    for row in rows[:500]:
        expected = CL.conditioned_lineage_checksum(
            CL.ConditionedLineageInput(
                c2_lineage_checksum=row["c2_lineage_checksum"],
                industry_id=row["industry_id"],
                commodity_series_id=row["commodity_series_id"],
                c3_exposure_checksum=row["c3_exposure_checksum"],
                exposure_value=row["exposure_value"],
                direction_sign=row["price_increase_to_stress_sign"],
                proxy_fit_status=row["proxy_fit_status"],
                eligibility_status=True,
                matrix_variant=row["matrix_variant"],
                transformation_version=CL.TRANSFORMATION_VERSION,
                structural_source_checksum=c3["io_source"]["sha256"],
            )
        )
        assert expected == row["conditioned_lineage_checksum"]
        checked += 1
    assert checked == 500


def test_missing_c2_or_c3_lineage_fails(c3):
    """Synthetic: an untraceable feature must never be emitted."""
    base = dict(
        c2_lineage_checksum="a" * 64, industry_id="IND-01",
        commodity_series_id="brent_crude_usd_bbl", c3_exposure_checksum="b" * 64,
        exposure_value=0.5, direction_sign=1,
        proxy_fit_status="broad_proxy_use_with_caution", eligibility_status=True,
        matrix_variant="primary_direct_lag2",
        transformation_version=CL.TRANSFORMATION_VERSION,
        structural_source_checksum="c" * 64,
    )
    assert CL.conditioned_lineage_checksum(CL.ConditionedLineageInput(**base))
    for field in ("c2_lineage_checksum", "c3_exposure_checksum",
                  "structural_source_checksum"):
        broken = dict(base)
        broken[field] = ""
        with pytest.raises(CL.ConditionedLineageError, match="Incomplete"):
            CL.conditioned_lineage_checksum(CL.ConditionedLineageInput(**broken))
    null_sign = dict(base)
    null_sign["direction_sign"] = None
    with pytest.raises(CL.ConditionedLineageError, match="non-null direction sign"):
        CL.conditioned_lineage_checksum(CL.ConditionedLineageInput(**null_sign))


def test_incomplete_c3_exposure_row_fails_lineage():
    with pytest.raises(CL.ConditionedLineageError, match="missing"):
        CL.exposure_row_checksum({"industry_id": "IND-01"})


def test_lineage_is_sensitive_to_every_component(c3):
    base = dict(
        c2_lineage_checksum="a" * 64, industry_id="IND-01",
        commodity_series_id="brent_crude_usd_bbl", c3_exposure_checksum="b" * 64,
        exposure_value=0.5, direction_sign=1,
        proxy_fit_status="broad_proxy_use_with_caution", eligibility_status=True,
        matrix_variant="primary_direct_lag2",
        transformation_version=CL.TRANSFORMATION_VERSION,
        structural_source_checksum="c" * 64,
    )
    reference = CL.conditioned_lineage_checksum(CL.ConditionedLineageInput(**base))
    for field, value in (
        ("exposure_value", 0.6), ("matrix_variant", "timing_sensitivity_direct_lag1"),
        ("proxy_fit_status", "fit_for_structural_use"), ("industry_id", "IND-02"),
    ):
        altered = dict(base)
        altered[field] = value
        assert CL.conditioned_lineage_checksum(
            CL.ConditionedLineageInput(**altered)
        ) != reference


# --- shared sector ------------------------------------------------------------


def test_aluminum_copper_shared_group_preserved(rows):
    shared = [r for r in rows if r["shared_io_source_sector"]]
    assert shared
    for row in shared:
        assert row["commodity_series_id"] in ("aluminum_usd_mt", "copper_usd_mt")
        assert row["shared_exposure_group"] == "io_sector_107"
        assert row["additive_aggregation_allowed"] is False
    unshared = [r for r in rows if not r["shared_io_source_sector"]]
    assert all(r["shared_exposure_group"] is None for r in unshared)
    assert all(r["additive_aggregation_allowed"] is True for r in unshared)


def test_summing_aluminum_and_copper_exposure_is_rejected(rows):
    """Synthetic: the validator must refuse a double-counted aggregate."""
    both = [
        r for r in rows
        if r["matrix_variant"] == "primary_direct_lag2"
        and r["industry_id"] == "IND-01"
        and r["base_feature_name"] == "price_level"
        and r["reference_month"] == "2024-01-01"
        and r["shared_io_source_sector"]
    ]
    assert len(both) == 2
    with pytest.raises(IC.ConditioningError, match="counted more than once"):
        IC.assert_no_duplicate_shared_sector_aggregate(both, "test aggregate")
    # One of the pair alone is fine.
    IC.assert_no_duplicate_shared_sector_aggregate(both[:1], "test aggregate")


def test_no_combined_non_ferrous_index_created(audit):
    shared = audit["shared_sector"]
    assert shared["combined_non_ferrous_index_created"] is False
    assert shared["pca_or_weighted_average_created"] is False
    assert shared["additive_aggregation_allowed"] is False
    assert shared["duplicate_aggregate_validator_fires"] is True
    assert CONFIG["shared_sector_policy"]["exposure_weights_summed"] is False
    assert CONFIG["shared_sector_policy"]["exposure_weights_averaged"] is False
    assert CONFIG["shared_sector_policy"]["independently_measured_claim"] is False


# --- development snapshot -----------------------------------------------------


def test_development_snapshot_dimensions(audit):
    dimensions = audit["development_snapshot"]["dimensions"]
    assert dimensions["origins"] == 15
    assert dimensions["industries"] == 12
    assert dimensions["industry_origin_rows"] == 180
    assert dimensions["commodity_feature_columns"] == 20
    assert dimensions["eligible_feature_cells"] == 3225
    assert dimensions["ineligible_feature_cells"] == 375
    assert dimensions["total_cells"] == 3600
    assert audit["development_snapshot"]["first_origin"] == "2024-01-01"
    assert audit["development_snapshot"]["last_origin"] == "2025-03-01"


def test_snapshot_uses_availability_metadata_not_positional_shift(rows, c3, audit):
    assert audit["development_snapshot"]["positional_shift_used"] is False
    assert "conditioned_available_month" in (
        audit["development_snapshot"]["selection_rule"]
    )
    industries = sorted({r["industry_id"] for r in c3["canonical_rows"]})
    commodities = sorted({r["commodity_series_id"] for r in c3["canonical_rows"]})
    features = sorted({r["base_feature_name"] for r in rows})
    eligible = {
        (r["industry_id"], r["commodity_series_id"])
        for r in c3["canonical_rows"] if r["industry_pair_feature_eligible"]
    }
    origins = FS.development_origins("2024-01-01", "2025-03-01")
    snapshot = FS.build_development_snapshot(
        rows, industries, commodities, features, eligible, origins
    )
    # Every observed cell must respect the availability rule.
    for entry in snapshot["rows"]:
        origin = entry["forecast_origin_month"]
        for key, value in entry.items():
            if key.endswith("__available_month"):
                assert value <= origin


def test_snapshot_ineligible_cells_are_null_with_a_mask(rows, c3):
    industries = sorted({r["industry_id"] for r in c3["canonical_rows"]})
    commodities = sorted({r["commodity_series_id"] for r in c3["canonical_rows"]})
    features = sorted({r["base_feature_name"] for r in rows})
    eligible = {
        (r["industry_id"], r["commodity_series_id"])
        for r in c3["canonical_rows"] if r["industry_pair_feature_eligible"]
    }
    origins = FS.development_origins("2024-01-01", "2025-03-01")
    snapshot = FS.build_development_snapshot(
        rows, industries, commodities, features, eligible, origins
    )
    ineligible = [m for m in snapshot["mask"] if not m["eligible"]]
    assert len(ineligible) == 375
    for entry in ineligible:
        assert entry["status"] == "structurally_ineligible"
    for row in snapshot["rows"]:
        for commodity, feature in (("aluminum_usd_mt", "price_level"),):
            if row["industry_id"] in ("IND-08", "IND-12"):
                column = f"{commodity}__{feature}"
                assert row[column] is None
                assert row[f"{column}__status"] == "structurally_ineligible"
    assert snapshot["cell_status_counts"]["structurally_ineligible"] == 375
    assert snapshot["cell_status_counts"]["observed"] == 3225


def test_snapshot_attaches_no_target_columns(audit, rows, c3):
    assert audit["development_snapshot"]["target_columns_attached"] is False
    industries = sorted({r["industry_id"] for r in c3["canonical_rows"]})
    commodities = sorted({r["commodity_series_id"] for r in c3["canonical_rows"]})
    features = sorted({r["base_feature_name"] for r in rows})
    eligible = {
        (r["industry_id"], r["commodity_series_id"])
        for r in c3["canonical_rows"] if r["industry_pair_feature_eligible"]
    }
    snapshot = FS.build_development_snapshot(
        rows, industries, commodities, features, eligible,
        FS.development_origins("2024-01-01", "2025-03-01"),
    )
    banned = ("target", "mpi", "stress", "risk_level", "prediction", "locked")
    for row in snapshot["rows"]:
        for column in row:
            assert not any(token in column.lower() for token in banned), column


# --- schema, wide output, scope ----------------------------------------------


def test_schema_matches_the_columns_actually_written(rows):
    declared = [column["name"] for column in SCHEMA["columns"]]
    assert declared == list(IC.CANONICAL_COLUMNS)
    assert set(rows[0]) == set(IC.CANONICAL_COLUMNS)
    assert SCHEMA["row_count"] == 39474
    assert SCHEMA["rows_per_variant"] == 13158


def test_no_target_risk_prediction_or_locked_test_fields(rows):
    for forbidden in SCHEMA["forbidden_columns"]:
        assert forbidden not in rows[0], forbidden
    banned = ("target", "mpi", "stress_score", "risk_level", "prediction",
              "locked", "correlation", "importance")
    for column in rows[0]:
        assert not any(token in column.lower() for token in banned), column


def test_wide_table_is_derived_and_has_no_conditioning_logic(rows):
    wide = IC.to_wide_table(rows, "primary_direct_lag2")
    assert len(wide) == 65 * 12
    index = {(r["reference_month"], r["industry_id"]): r for r in wide}
    for row in rows:
        if row["matrix_variant"] != "primary_direct_lag2":
            continue
        cell = index[(row["reference_month"], row["industry_id"])]
        column = f"{row['commodity_series_id']}__{row['base_feature_name']}"
        assert cell[column] == row["conditioned_feature_value"]
        assert cell[f"{column}__zero_reason"] == row["zero_reason"]
    source = (ROOT / "src" / "thai_supply_chain_ews" / "features" /
              "industry_conditioning.py").read_text(encoding="utf-8")
    wide_source = source[source.index("def to_wide_table"):]
    for forbidden in ("conditioned_lineage_checksum(", "* sign", "* exposure"):
        assert forbidden not in wide_source, forbidden


def test_deterministic_long_and_wide(c2_rows, c3, availability):
    first = IC.build_conditioned_matrix(
        c2_rows, c3["canonical_rows"], availability, c3["io_source"]["sha256"]
    )
    second = IC.build_conditioned_matrix(
        c2_rows, c3["canonical_rows"], availability, c3["io_source"]["sha256"]
    )
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )
    assert IC.to_wide_table(first, "primary_direct_lag2") == IC.to_wide_table(
        second, "primary_direct_lag2"
    )


def test_model_feature_approval_stays_false(rows, audit):
    assert audit["model_feature_approved_set"] is False
    assert CONFIG["approval_state"]["model_feature_approved"] is False
    assert CONFIG["approval_state"]["feature_semantics_approved"] is False
    assert all(r["model_feature_approved"] is False for r in rows)


def test_script_takes_no_arguments_and_calls_the_package():
    script = (ROOT / "scripts" / "run_c4_industry_conditioned_features.py").read_text(
        encoding="utf-8"
    )
    assert "argparse" not in script
    assert "sys.argv" not in script
    assert "IC.build_conditioned_matrix" in script
    assert "FS.build_development_snapshot" in script
    for forbidden in ("targets.production_stress", "evaluation.walk_forward",
                      "evaluation.baselines"):
        assert forbidden not in script


def test_generated_parquet_is_git_ignored(audit):
    for output in audit["outputs"].values():
        result = subprocess.run(
            ["git", "check-ignore", output["path"]],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, output["path"]


def test_upstream_artifacts_unchanged():
    """C4 writes only its own artifacts."""
    upstream = {
        "docs/b1_ingestion_metadata.json", "docs/b3_target_build_metadata.json",
        "docs/b4_baseline_results.json", "docs/b4_locked_test_manifest.json",
        "docs/c1_commodity_source_audit.json",
        "docs/c1_5_commodity_timing_audit.json",
        "docs/c2_commodity_feature_audit.json",
        "docs/c3_commodity_exposure_matrix.json",
        "docs/c3_io_source_audit.json",
    }
    for relative in upstream:
        assert (ROOT / relative).is_file(), relative
    written = {
        "docs/c4_industry_conditioned_feature_audit.json",
        "configs/industry_conditioned_features.yaml",
        "schemas/industry_conditioned_feature.schema.yaml",
    }
    assert not (upstream & written)


def test_c2_and_c3_values_pass_through_unchanged(rows, c2_rows, c3):
    """C4 multiplies; it never edits an input."""
    c2_index = {
        (r["series_id"], r["feature_name"], r["reference_month"], r["availability_policy"]): r
        for policy_rows in c2_rows.values() for r in policy_rows
    }
    c3_index = {
        (r["industry_id"], r["commodity_series_id"]): r for r in c3["canonical_rows"]
    }
    for row in rows[:1000]:
        base = c2_index[(
            row["commodity_series_id"], row["base_feature_name"],
            row["reference_month"], row["availability_policy"],
        )]
        assert row["base_feature_value"] == base["feature_value"]
        assert row["c2_lineage_checksum"] == base["input_lineage_checksum"]
        exposure = c3_index[(row["industry_id"], row["commodity_series_id"])]
        assert row["exposure_value"] == exposure[row["exposure_variant"]]
