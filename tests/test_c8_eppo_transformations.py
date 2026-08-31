"""Task C8 tests — EPPO fuel-oil source-level transformations.

A transformation table is easy to get plausibly wrong. A ``ddof=1`` inflates
every volatility by 22% and still looks like volatility. A ``log10`` scales every
change by 0.434 and still looks like a change. A forward-filled April produces a
May value that looks exactly like a real one. None of those failures announce
themselves, so most of this file constructs them deliberately and requires an
explicit raise.

The other half guards the boundary C7.5 drew. Only two series are authorized;
H-DIESEL is not. The two fuel oils share one I/O sector coefficient and may
never be added, averaged or requested together. And a source-level transformation
is not a model feature — ``model_feature_approved`` is false on all 650 rows and
nothing here reads an exposure coefficient, a target or a model.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.features import eppo_fuel_oil_transformations as T
from thai_supply_chain_ews.features import eppo_transformation_availability as AV
from thai_supply_chain_ews.features import eppo_transformation_lineage as LIN

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "eppo_fuel_oil_transformations.yaml").read_text(encoding="utf-8")
)
AUDIT = ROOT / "docs" / "c8_eppo_transformation_audit.json"
C7_5_DECISION = ROOT / "docs" / "c7_5_eppo_semantic_decision.json"
SEMANTIC_PARQUET = ROOT / "data" / "interim" / "c7_5_eppo_monthly_semantic.parquet"
FEATURE_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"

FO600 = "eppo_ex_refinery_fo600_2s"
FO1500 = "eppo_ex_refinery_fo1500_2s"
HSD = "eppo_ex_refinery_hsd"
CH600 = "eppo_fo600_channel"
CH1500 = "eppo_fo1500_channel"

requires_run = pytest.mark.skipif(not AUDIT.is_file(), reason="C8 has not been run")
requires_parquet = pytest.mark.skipif(
    not FEATURE_PARQUET.is_file(), reason="the C8 feature table is not present"
)


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def _table():
    import pandas as pd

    frame = pd.read_parquet(FEATURE_PARQUET)
    rows = frame.to_dict("records")
    for row in rows:
        value = row["feature_value"]
        row["feature_value"] = None if value is None or pd.isna(value) else float(value)
        for column in ("required_input_months", "missing_input_months",
                       "source_monthly_lineage_checksums"):
            row[column] = [str(x) for x in (row[column] if row[column] is not None else [])]
        if row["source_available_as_of"] is not None and pd.isna(
            row["source_available_as_of"]
        ):
            row["source_available_as_of"] = None
    return rows


# ===========================================================================
# Fixtures: a synthetic source series, so a formula test never depends on the
# live archive being present.
# ===========================================================================
def _source(series_id=FO600, values=None, gaps=(), start="2021-01", months=65):
    calendar = T.month_range(start, T.shift_month(start, months - 1))
    values = values or {m: 10.0 + index for index, m in enumerate(calendar)}
    observations = []
    for month in calendar:
        missing = month in gaps
        observations.append(T.SourceMonth(
            series_id=series_id,
            reference_month=month,
            monthly_value_strict=None if missing else float(values[month]),
            approved_transformation_input=not missing,
            source_product_label="FO 600 (1) 2%S",
            canonical_product_id=series_id,
            aggregation_rule_version="c7_v1",
            aggregation_status=(
                "known_document_gap" if missing else "approved_complete_inventory"
            ),
            monthly_lineage_checksum="a" * 64,
            policy_available_month=T.shift_month(month, 2),
        ))
    return observations


def _grid(observations, series_ids=(FO600,), start="2021-01", months=65):
    calendar = T.month_range(start, T.shift_month(start, months - 1))
    records = {}

    def policy_month(window):
        return AV.transformation_policy_available_month(window)

    def lineage(row, index):
        available = [
            LIN.source_input_lineage(index[(row.series_id, month)])
            for month in row.required_input_months
            if (row.series_id, month) in index and month not in row.missing_input_months
        ]
        record = LIN.transformation_lineage_record(
            transformation_id=row.transformation_id,
            transformation_formula_version=row.transformation_formula_version,
            channel_id=row.channel_id, reference_month=row.reference_month,
            required_input_months=row.required_input_months,
            available_inputs=available,
            missing_input_months=row.missing_input_months,
            feature_value=row.feature_value,
            transformation_status=row.transformation_status,
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
            feature_unit=row.feature_unit,
        )
        records[(row.channel_id, row.reference_month, row.transformation_id)] = record
        return LIN.transformation_lineage_checksum(record)

    rows = T.build_transformation_grid(
        observations, series_ids, calendar, start, policy_month, lineage
    )
    return rows, records


def _cell(rows, month, transformation_id, channel_id=CH600):
    return next(
        r for r in rows
        if (r.reference_month if hasattr(r, "reference_month") else r["reference_month"])
        == month
        and (r.transformation_id if hasattr(r, "transformation_id")
             else r["transformation_id"]) == transformation_id
        and (r.channel_id if hasattr(r, "channel_id") else r["channel_id"]) == channel_id
    )


# ===========================================================================
# 1. C7.5 invariants
# ===========================================================================
@requires_run
def test_all_c7_5_invariants_reproduced():
    invariants = _audit()["c7_5_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 22
    for name, check in invariants["checks"].items():
        assert check["reproduced"] is True, name


@requires_run
def test_c7_5_headline_facts_match_the_brief():
    checks = _audit()["c7_5_invariants"]["checks"]
    expected = {
        "semantic_monthly_rows": 195,
        "approved_complete_inventory_rows": 168,
        "approved_with_source_label_variant_rows": 8,
        "semantic_definition_gap_rows": 16,
        "known_document_gap_rows": 3,
        "fo600_equivalence_established": "equivalence_established",
        "fo1500_equivalence_established": "equivalence_established",
        "raw_labels_preserved": False,
        "hsd_not_transformation_ready": False,
        "fo600_transformation_ready": True,
        "fo1500_transformation_ready": True,
        "fo600_strict_null_2026_04": None,
        "fo1500_strict_null_2026_04": None,
        "operational_policy_lag_months": 2,
        "operational_lag_is_measured": False,
        "simultaneous_additive_fuel_oil_use_prohibited": False,
    }
    for name, value in expected.items():
        assert checks[name]["actual"] == value, name
    assert checks["reference_month_range"]["actual"] == ["2021-01", "2026-05"]
    assert checks["fo_variant_months_2024_07_to_2024_10"]["actual"] == [
        "2024-07", "2024-08", "2024-09", "2024-10",
    ]
    assert checks["hsd_gap_2023_09_to_2024_12"]["actual"] == ["2023-09", "2024-12", 16]


def test_authorizations_and_timing_policy_are_inherited_unchanged():
    authorizations = CONFIG["authorizations"]
    assert authorizations["c8_fo600_transformation_authorized"] is True
    assert authorizations["c8_fo1500_transformation_authorized"] is True
    for key in ("c8_hsd_transformation_authorized",
                "c8_industry_conditioning_authorized", "c8_target_join_authorized",
                "c8_modeling_authorized", "c8_imputation_authorized",
                "c8_outcome_based_channel_selection_authorized",
                "c8_simultaneous_additive_fuel_oil_use_authorized",
                "c8_locked_test_evaluation_authorized"):
        assert authorizations[key] is False, key
    policy = CONFIG["timing_policy"]
    assert policy["latest_vintage_values_used"] is True
    assert policy["historical_release_timing_verified"] is False
    assert policy["point_in_time_values_supported"] is False
    assert policy["fully_real_time_backtest"] is False
    assert policy["minimum_verified_publication_lag_months"] is None
    assert policy["operational_policy_lag_months"] == 2
    assert policy["operational_lag_is_measured"] is False
    assert policy["availability_basis"] == (
        "conservative_policy_not_historical_measurement"
    )
    for key, value in CONFIG["provenance"].items():
        assert value is False, key
    for key, value in CONFIG["preserved_decisions"].items():
        assert value is False, key


# ===========================================================================
# 2. Authorized series only
# ===========================================================================
def test_only_the_two_fuel_oils_are_authorized():
    assert T.AUTHORIZED_SERIES == (FO600, FO1500)
    assert HSD not in T.AUTHORIZED_SERIES
    assert set(T.CHANNEL_BY_SERIES) == {FO600, FO1500}
    assert set(T.SERIES_BY_CHANNEL) == {CH600, CH1500}


def test_h_diesel_is_rejected_as_an_input():
    observation = T.SourceMonth(
        series_id=HSD, reference_month="2022-05", monthly_value_strict=25.0,
        approved_transformation_input=True,
    )
    with pytest.raises(T.UnauthorizedSeriesError, match="not authorized"):
        T.assert_strict_input(observation)


def test_h_diesel_cannot_enter_the_grid():
    with pytest.raises(T.UnauthorizedSeriesError, match="no authorized C8 channel"):
        _grid(_source(series_id=HSD, months=6), series_ids=(HSD,), months=6)


def test_an_unapproved_month_is_rejected_as_an_input():
    observation = T.SourceMonth(
        series_id=FO600, reference_month="2026-04", monthly_value_strict=20.0,
        approved_transformation_input=False,
    )
    with pytest.raises(T.TransformationError, match="not an approved"):
        T.assert_strict_input(observation)


def test_a_wrong_unit_is_rejected():
    observation = T.SourceMonth(
        series_id=FO600, reference_month="2022-05", monthly_value_strict=20.0,
        approved_transformation_input=True, unit="BAHT/KILOGRAM",
    )
    with pytest.raises(T.TransformationError, match="is not 'BAHT/LITRE'"):
        T.assert_strict_input(observation)


# ===========================================================================
# 3. The formulas
# ===========================================================================
def test_log_change_uses_the_natural_logarithm_scaled_by_100():
    value = T.compute_transformation("log_change_1m_pct", [10.0, 20.0])
    assert value == pytest.approx(100.0 * math.log(2.0))
    assert value == pytest.approx(69.31471805599453)
    # A base-10 logarithm would give 30.10; a simple percentage change 100.0.
    assert value != pytest.approx(100.0 * math.log10(2.0))
    assert value != pytest.approx(100.0)


def test_three_and_twelve_month_changes_are_endpoint_definitions():
    prices = [10.0, 11.0, 12.5, 13.0]
    three = T.compute_transformation("log_change_3m_pct", [prices[0], prices[-1]])
    assert three == pytest.approx(100.0 * (math.log(13.0) - math.log(10.0)))
    # Not a sum of rounded monthly changes: that route is a different number.
    rounded = sum(
        round(100.0 * (math.log(b) - math.log(a)), 2)
        for a, b in zip(prices[:-1], prices[1:], strict=True)
    )
    assert three != pytest.approx(rounded, abs=1e-9) or rounded == three
    twelve = T.compute_transformation("log_change_12m_pct", [8.0, 16.0])
    assert twelve == pytest.approx(100.0 * math.log(2.0))


def test_realized_volatility_uses_four_price_levels_and_ddof_zero():
    assert T.REQUIRED_INPUT_LAGS["realized_volatility_3m_pct"] == (3, 2, 1, 0)
    assert len(T.required_input_months("realized_volatility_3m_pct", "2025-08")) == 4
    prices = [10.0, 11.0, 12.0, 12.5]
    changes = [
        100.0 * (math.log(b) - math.log(a)) for a, b in zip(prices[:-1], prices[1:], strict=True)
    ]
    mean = sum(changes) / 3
    population = math.sqrt(sum((c - mean) ** 2 for c in changes) / 3)
    sample = math.sqrt(sum((c - mean) ** 2 for c in changes) / 2)
    value = T.compute_transformation("realized_volatility_3m_pct", prices)
    assert value == pytest.approx(population)
    assert value != pytest.approx(sample)
    assert sample / value == pytest.approx(math.sqrt(3 / 2))


def test_price_level_is_the_month_itself():
    assert T.compute_transformation("price_level", [17.25]) == 17.25
    assert T.required_input_months("price_level", "2024-03") == ["2024-03"]


def test_required_input_months_are_declared_not_inferred():
    assert T.required_input_months("log_change_1m_pct", "2024-03") == [
        "2024-02", "2024-03",
    ]
    assert T.required_input_months("log_change_3m_pct", "2024-03") == [
        "2023-12", "2024-03",
    ]
    assert T.required_input_months("log_change_12m_pct", "2024-03") == [
        "2023-03", "2024-03",
    ]
    assert T.required_input_months("realized_volatility_3m_pct", "2024-03") == [
        "2023-12", "2024-01", "2024-02", "2024-03",
    ]


def test_nonpositive_and_nonfinite_inputs_raise():
    for prices in ([0.0, 10.0], [-1.0, 10.0], [10.0, 0.0], [math.inf, 10.0],
                   [math.nan, 10.0]):
        with pytest.raises(T.TransformationError):
            T.compute_transformation("log_change_1m_pct", prices)
    for value in (0.0, -3.0, math.inf, math.nan):
        observation = T.SourceMonth(
            series_id=FO600, reference_month="2022-05", monthly_value_strict=value,
            approved_transformation_input=True,
        )
        with pytest.raises(T.TransformationError):
            T.assert_strict_input(observation)
    text = T.SourceMonth(
        series_id=FO600, reference_month="2022-05", monthly_value_strict="20.0",
        approved_transformation_input=True,
    )
    with pytest.raises(T.TransformationError, match="not a numeric price"):
        T.assert_strict_input(text)


def test_a_wrong_sized_price_window_raises():
    with pytest.raises(T.TransformationError, match="needs 4 price levels"):
        T.compute_transformation("realized_volatility_3m_pct", [10.0, 11.0, 12.0])
    with pytest.raises(T.TransformationError, match="needs 2 price levels"):
        T.compute_transformation("log_change_1m_pct", [10.0])


def test_duplicate_source_keys_raise():
    observations = _source(months=4) + _source(months=1)
    with pytest.raises(T.TransformationError, match="duplicate"):
        _grid(observations, months=4)


# ===========================================================================
# 4. The grid and its counts
# ===========================================================================
@requires_run
def test_the_grid_is_exactly_650_rows():
    totals = _audit()["counts"]["totals"]
    assert totals["feature_grid_rows"] == 650
    assert totals["finite_feature_rows"] == 598
    assert totals["null_feature_rows"] == 52
    assert _audit()["counts"]["counts_reconciled"] is True


@requires_run
def test_counts_by_transformation_and_channel_match_the_preregistered_table():
    counts = _audit()["counts"]
    expected = {
        "price_level": (64, 1),
        "log_change_1m_pct": (62, 3),
        "log_change_3m_pct": (61, 4),
        "log_change_12m_pct": (52, 13),
        "realized_volatility_3m_pct": (60, 5),
    }
    for name, (finite, null_rows) in expected.items():
        assert counts["preregistered"]["per_series"][name] == {
            "finite": finite, "null_rows": null_rows,
        }, name
        assert counts["derived_from_declared_lags"][name] == {
            "finite": finite, "null_rows": null_rows,
        }, name
        for channel in (CH600, CH1500):
            assert counts["observed_by_channel"][channel][name] == {
                "finite": finite, "null_rows": null_rows,
            }, (channel, name)
    assert counts["counts_altered_after_observing_output"] is False


def test_expected_counts_are_derived_from_the_declared_lags():
    derived = T.expected_counts()
    assert derived["price_level"] == {"finite": 64, "null_rows": 1}
    assert derived["log_change_1m_pct"] == {"finite": 62, "null_rows": 3}
    assert derived["log_change_3m_pct"] == {"finite": 61, "null_rows": 4}
    assert derived["log_change_12m_pct"] == {"finite": 52, "null_rows": 13}
    assert derived["realized_volatility_3m_pct"] == {"finite": 60, "null_rows": 5}
    assert derived["total"] == {"finite": 299, "null_rows": 26}
    # No gap at all would make every window computable from the calendar alone.
    ungapped = T.expected_counts(gap_months=())
    assert ungapped["price_level"]["finite"] == 65
    assert ungapped["total"]["finite"] == 65 + 64 + 62 + 53 + 62


def test_a_synthetic_grid_has_no_missing_or_duplicate_keys():
    rows, _ = _grid(_source(gaps=("2026-04",)))
    keys = [(r.channel_id, r.reference_month, r.transformation_id) for r in rows]
    assert len(keys) == 325 == len(set(keys))
    assert keys == sorted(keys)


# ===========================================================================
# 5. Missingness propagation
# ===========================================================================
def test_missing_source_month_propagates_to_every_dependent_window():
    rows, _ = _grid(_source(gaps=("2026-04",)))
    assert _cell(rows, "2026-04", "price_level").transformation_status == (
        "current_month_source_gap"
    )
    assert _cell(rows, "2026-05", "log_change_1m_pct").transformation_status == (
        "input_window_source_gap"
    )
    assert _cell(rows, "2026-05", "realized_volatility_3m_pct").transformation_status == (
        "input_window_source_gap"
    )
    for month, transformation in (("2026-05", "log_change_1m_pct"),
                                  ("2026-05", "realized_volatility_3m_pct"),
                                  ("2026-04", "price_level")):
        cell = _cell(rows, month, transformation)
        assert cell.feature_value is None
        assert "2026-04" in cell.missing_input_months


def test_insufficient_history_is_distinct_from_a_source_gap():
    rows, _ = _grid(_source(gaps=("2026-04",)))
    assert _cell(rows, "2021-01", "log_change_1m_pct").transformation_status == (
        "insufficient_feature_history"
    )
    assert _cell(rows, "2021-12", "log_change_12m_pct").transformation_status == (
        "insufficient_feature_history"
    )
    assert _cell(rows, "2022-01", "log_change_12m_pct").transformation_status == (
        "available_numeric"
    )
    assert _cell(rows, "2021-01", "price_level").transformation_status == (
        "available_numeric"
    )
    statuses = {r.transformation_status for r in rows}
    assert "insufficient_feature_history" in statuses
    assert statuses <= set(T.TRANSFORMATION_STATUSES)


def test_status_precedence_is_declared_and_total():
    assert list(T.TRANSFORMATION_STATUSES) == CONFIG["missingness"]["status_precedence"]
    assert CONFIG["missingness"]["partial_input_window_permitted"] is False
    assert CONFIG["missingness"]["insufficient_prehistory_labelled_as_source_gap"] is False


def test_no_value_is_produced_from_a_partial_window():
    rows, _ = _grid(_source(gaps=("2023-06",)))
    for row in rows:
        if row.feature_value is None:
            assert row.missing_input_months, (row.reference_month, row.transformation_id)
        else:
            assert row.missing_input_months == []
            assert row.available_input_count == row.required_input_count


def test_no_imputation_interpolation_or_fill_occurs():
    values = {m: 10.0 for m in T.month_range("2021-01", "2026-05")}
    rows, _ = _grid(_source(values=values, gaps=("2023-06",)))
    june = _cell(rows, "2023-06", "price_level")
    assert june.feature_value is None
    # A forward fill, a backward fill or an interpolation would all have made
    # this 10.0, which is exactly what every neighbouring month holds.
    assert june.feature_value != 10.0
    july = _cell(rows, "2023-07", "log_change_1m_pct")
    assert july.feature_value is None


def test_no_substitution_from_the_other_fuel_oil():
    # A 12-month synthetic window starting 2021-01, so the gap month has to be
    # inside it: 2021-06.
    observations = (
        _source(series_id=FO600, gaps=("2021-06",), months=12)
        + _source(series_id=FO1500, months=12)
    )
    rows, _ = _grid(observations, series_ids=(FO600, FO1500), months=12)
    gapped = _cell(rows, "2021-06", "price_level", CH600)
    other = _cell(rows, "2021-06", "price_level", CH1500)
    assert gapped.feature_value is None
    assert other.feature_value is not None


@requires_run
def test_every_null_cell_is_reported_with_its_status():
    missingness = _audit()["missingness"]
    assert sum(missingness["status_counts"].values()) == 650
    assert missingness["status_counts"]["available_numeric"] == 598
    nulls = sum(v for k, v in missingness["status_counts"].items()
                if k != "available_numeric")
    assert nulls == 52
    assert missingness["status_counts"]["insufficient_feature_history"] == 38
    assert missingness["status_counts"]["current_month_source_gap"] == 10
    assert missingness["status_counts"]["input_window_source_gap"] == 4


@requires_parquet
def test_april_and_may_2026_behaviour_in_the_real_table():
    rows = _table()
    for channel in (CH600, CH1500):
        for transformation in T.TRANSFORMATION_IDS:
            april = _cell(rows, "2026-04", transformation, channel)
            assert april["feature_value"] is None, (channel, transformation)
            assert april["transformation_status"] == "current_month_source_gap"
            assert "2026-04" in april["missing_input_months"]
        for transformation in ("log_change_1m_pct", "realized_volatility_3m_pct"):
            may = _cell(rows, "2026-05", transformation, channel)
            assert may["feature_value"] is None, (channel, transformation)
            assert may["transformation_status"] == "input_window_source_gap"
            assert may["missing_input_months"] == ["2026-04"]
        for transformation in ("price_level", "log_change_3m_pct", "log_change_12m_pct"):
            may = _cell(rows, "2026-05", transformation, channel)
            assert may["feature_value"] is not None, (channel, transformation)
            assert may["transformation_status"] == "available_numeric"


# ===========================================================================
# 6. Strict input only
# ===========================================================================
def test_only_the_strict_monthly_value_is_carried_into_a_transformation():
    assert "monthly_value_strict" in T.SourceMonth.__dataclass_fields__
    assert "monthly_value_descriptive" not in T.SourceMonth.__dataclass_fields__
    assert CONFIG["input"]["value_field"] == "monthly_value_strict"
    assert "monthly_value_descriptive" in CONFIG["input"]["never_use"]


@requires_run
def test_the_runner_records_that_it_read_no_descriptive_value():
    inputs = _audit()["input"]
    assert inputs["value_field"] == "monthly_value_strict"
    assert inputs["descriptive_value_read"] is False
    assert inputs["hsd_read"] is False
    assert inputs["source_months_loaded"] == 130
    assert inputs["approved_transformation_inputs"] == 128
    assert inputs["strict_gaps"] == ["2026-04"]


def test_a_descriptive_value_cannot_be_smuggled_in_as_strict():
    source = (ROOT / "scripts" / "run_c8_eppo_transformations.py").read_text(
        encoding="utf-8")
    assert "monthly_value_descriptive" not in source
    module = (ROOT / "src" / "thai_supply_chain_ews" / "features"
              / "eppo_fuel_oil_transformations.py").read_text(encoding="utf-8")
    assert "monthly_value_descriptive" not in module


# ===========================================================================
# 7. Availability
# ===========================================================================
def test_policy_month_is_the_maximum_over_the_declared_window():
    assert AV.transformation_policy_available_month(["2024-01"]) == "2024-03"
    assert AV.transformation_policy_available_month(
        ["2023-03", "2024-03"]
    ) == "2024-05"
    assert AV.transformation_policy_available_month(
        ["2023-12", "2024-01", "2024-02", "2024-03"]
    ) == "2024-05"
    with pytest.raises(AV.AvailabilityPolicyError):
        AV.transformation_policy_available_month([])


def test_the_reference_plus_two_equality_is_verified_not_assumed():
    AV.assert_policy_month_matches_reference_rule("2024-03", "2024-05")
    with pytest.raises(AV.AvailabilityPolicyError, match="policy over the declared"):
        AV.assert_policy_month_matches_reference_rule("2024-03", "2024-04")
    with pytest.raises(AV.AvailabilityPolicyError):
        AV.assert_policy_month_matches_reference_rule("2024-03", "2024-06")


def test_source_availability_stays_null_and_the_lag_stays_policy():
    AV.assert_policy_month_is_not_a_release_date(
        {"source_available_as_of": None, "operational_lag_is_measured": False,
         "availability_basis": AV.AVAILABILITY_BASIS}
    )
    with pytest.raises(AV.AvailabilityPolicyError, match="not a release date"):
        AV.assert_policy_month_is_not_a_release_date(
            {"source_available_as_of": "2024-05-15"}
        )
    with pytest.raises(AV.AvailabilityPolicyError, match="conservative project policy"):
        AV.assert_policy_month_is_not_a_release_date(
            {"source_available_as_of": None, "operational_lag_is_measured": True}
        )
    with pytest.raises(AV.AvailabilityPolicyError, match="availability_basis"):
        AV.assert_policy_month_is_not_a_release_date(
            {"source_available_as_of": None, "operational_lag_is_measured": False,
             "availability_basis": "verified_historical_measurement"}
        )


@pytest.mark.parametrize("issue_month,latest", [
    ("2024-01", "2023-11"), ("2025-03", "2025-01"), ("2026-04", "2026-02"),
])
def test_latest_permitted_reference_month_examples(issue_month, latest):
    assert AV.latest_permitted_reference_month(issue_month) == latest


@requires_parquet
def test_every_row_keeps_the_availability_contract():
    for row in _table():
        assert row["source_available_as_of"] is None
        assert row["availability_basis"] == (
            "conservative_policy_not_historical_measurement"
        )
        assert bool(row["latest_vintage_used"]) is True
        assert bool(row["point_in_time_supported"]) is False
        assert bool(row["operational_lag_is_measured"]) is False
        assert row["policy_available_month"] == T.shift_month(row["reference_month"], 2)


# ===========================================================================
# 8. The selector
# ===========================================================================
@requires_parquet
def test_selector_returns_only_numeric_rows_within_the_cutoff():
    rows = _table()
    selected = AV.select_source_transformations_available_at_issue(
        rows, "2025-03", CH600
    )
    assert selected
    assert all(r["feature_value"] is not None for r in selected)
    assert all(r["transformation_status"] == "available_numeric" for r in selected)
    assert all(r["channel_id"] == CH600 for r in selected)
    months = {r["reference_month"] for r in selected}
    assert max(months) == "2025-01"
    assert "2025-02" not in months
    assert "2025-03" not in months


@requires_parquet
def test_selector_rejects_a_request_naming_both_channels():
    rows = _table()
    with pytest.raises(T.TransformationError, match="mutually exclusive"):
        AV.select_source_transformations_available_at_issue(
            rows, "2025-03", [CH600, CH1500]
        )
    with pytest.raises(T.TransformationError, match="names no fuel-oil channel"):
        AV.select_source_transformations_available_at_issue(rows, "2025-03", [])


@requires_parquet
def test_selector_never_returns_a_null_row():
    rows = _table()
    for issue in ("2026-06", "2026-07"):
        selected = AV.select_source_transformations_available_at_issue(
            rows, issue, CH600
        )
        assert all(r["feature_value"] is not None for r in selected)
        assert not any(r["reference_month"] == "2026-04" for r in selected)


def test_selector_raises_on_a_mis_stamped_row():
    row = {
        "channel_id": CH600, "reference_month": "2024-01",
        "policy_available_month": "2024-02", "feature_value": 1.0,
        "transformation_status": "available_numeric",
        "source_available_as_of": None, "operational_lag_is_measured": False,
        "availability_basis": AV.AVAILABILITY_BASIS,
    }
    with pytest.raises(AV.AvailabilityPolicyError):
        AV.select_source_transformations_available_at_issue([row], "2024-06", CH600)


def test_selector_reads_no_target_or_model_artifact():
    source = (ROOT / "src" / "thai_supply_chain_ews" / "features"
              / "eppo_transformation_availability.py").read_text(encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)


# ===========================================================================
# 9. Issue-key audit
# ===========================================================================
@requires_run
def test_issue_key_coverage_is_reported_per_split_without_targets():
    coverage = _audit()["issue_key_coverage"]
    assert set(coverage) == {"development", "purge", "locked_test"}
    for split_name, per_channel in coverage.items():
        assert set(per_channel) == {CH600, CH1500}, split_name
        for entry in per_channel.values():
            assert entry["issue_months"] > 0
            assert entry["target_values_read"] is False
    assert coverage["development"][CH600]["issue_months"] == 15
    assert coverage["purge"][CH600]["issue_months"] == 3
    assert coverage["locked_test"][CH600]["issue_months"] == 10


@requires_run
def test_april_2026_is_unused_but_still_documented():
    april = _audit()["april_2026"]
    assert april["selected_by_any_registered_issue_key"] is False
    assert april["selections"] == []
    assert april["null_rows_retained_in_the_grid"] == 10
    assert april["removed_because_operationally_unused"] is False
    assert CONFIG["issue_key_audit"][
        "april_2026_gap_removed_because_operationally_unused"] is False


@requires_run
def test_the_audit_reads_no_target_or_prediction():
    audit = CONFIG["issue_key_audit"]
    for forbidden in ("target_values", "risk_levels", "target_distributions",
                      "model_predictions", "locked_test_outcomes"):
        assert forbidden in audit["never_reads"], forbidden


# ===========================================================================
# 10. Lineage
# ===========================================================================
def test_a_null_row_still_carries_complete_lineage():
    rows, records = _grid(_source(gaps=("2026-04",)))
    cell = _cell(rows, "2026-05", "log_change_1m_pct")
    record = records[(cell.channel_id, cell.reference_month, cell.transformation_id)]
    assert record["expected_input_months"] == ["2026-04", "2026-05"]
    assert record["available_input_months"] == ["2026-05"]
    assert record["missing_input_months"] == ["2026-04"]
    assert record["missingness_reason"] == "input_window_source_gap"
    assert record["output_value"] is None
    assert cell.transformation_lineage_checksum


def test_lineage_records_every_declared_source_field():
    rows, records = _grid(_source())
    cell = _cell(rows, "2024-03", "realized_volatility_3m_pct")
    record = records[(cell.channel_id, cell.reference_month, cell.transformation_id)]
    assert len(record["source_inputs"]) == 4
    for item in record["source_inputs"]:
        for field in LIN.SOURCE_INPUT_FIELDS:
            assert field in item, field
    assert record["transformation_id"] == "realized_volatility_3m_pct"
    assert record["channel_id"] == CH600
    assert record["input_ordering"] == "chronological_oldest_first_as_declared"
    assert record["availability_policy_version"] == AV.AVAILABILITY_POLICY_VERSION


def test_lineage_is_deterministic_and_content_sensitive():
    rows_a, records_a = _grid(_source())
    rows_b, records_b = _grid(_source())
    assert [r.transformation_lineage_checksum for r in rows_a] == [
        r.transformation_lineage_checksum for r in rows_b
    ]
    values = {m: 10.0 + i for i, m in enumerate(T.month_range("2021-01", "2026-05"))}
    values["2024-03"] = 99.0
    rows_c, _ = _grid(_source(values=values))
    assert [r.transformation_lineage_checksum for r in rows_a] != [
        r.transformation_lineage_checksum for r in rows_c
    ]
    _ = records_a, records_b


def test_two_nulls_with_different_causes_do_not_collide():
    rows, _ = _grid(_source(gaps=("2026-04",)))
    history = _cell(rows, "2021-01", "log_change_1m_pct")
    gap = _cell(rows, "2026-05", "log_change_1m_pct")
    assert history.feature_value is None and gap.feature_value is None
    assert (history.transformation_lineage_checksum
            != gap.transformation_lineage_checksum)


def test_lineage_refuses_a_value_produced_from_a_partial_window():
    with pytest.raises(LIN.EppoTransformationLineageError, match="partial input window"):
        LIN.transformation_lineage_record(
            transformation_id="log_change_1m_pct",
            transformation_formula_version=T.TRANSFORMATION_FORMULA_VERSION,
            channel_id=CH600, reference_month="2026-05",
            required_input_months=["2026-04", "2026-05"],
            available_inputs=[LIN.SourceInputLineage(FO600, "2026-05", 24.0)],
            missing_input_months=["2026-04"], feature_value=3.7,
            transformation_status="available_numeric",
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
        )


def test_lineage_refuses_an_unaccounted_input_window():
    with pytest.raises(LIN.EppoTransformationLineageError, match="does not account"):
        LIN.transformation_lineage_record(
            transformation_id="log_change_1m_pct",
            transformation_formula_version=T.TRANSFORMATION_FORMULA_VERSION,
            channel_id=CH600, reference_month="2026-05",
            required_input_months=["2026-04", "2026-05"],
            available_inputs=[], missing_input_months=[], feature_value=None,
            transformation_status="input_window_source_gap",
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
        )


@requires_run
def test_reported_lineage_covers_every_row():
    lineage = _audit()["lineage"]
    assert lineage["rows_with_a_checksum"] == 650
    assert lineage["null_rows_with_complete_lineage"] == 52
    assert lineage["distinct_checksums"] == 650
    assert lineage["lineage_version"] == LIN.LINEAGE_VERSION


# ===========================================================================
# 11. Channels
# ===========================================================================
def test_the_two_channels_are_never_combined():
    assert T.assert_single_fuel_oil_channel([CH600], "level") == CH600
    for operation in ("sum", "simple average", "composite index", "pca"):
        with pytest.raises(T.TransformationError, match="mutually exclusive"):
            T.assert_single_fuel_oil_channel([CH600, CH1500], operation)
    with pytest.raises(T.TransformationError, match="unknown fuel-oil channel"):
        T.assert_single_fuel_oil_channel(["eppo_hsd_channel"], "level")


def test_channel_restrictions_are_declared():
    restrictions = CONFIG["channel_restrictions"]
    for key in ("additive_aggregation_allowed", "simple_average_allowed",
                "automatic_composite_index_allowed",
                "simultaneous_model_entry_approved",
                "outcome_based_channel_selection_allowed"):
        assert restrictions[key] is False, key
    for construction in ("combined_fuel_oil_index", "mean_of_fo600_and_fo1500",
                         "sum_of_their_features", "weighted_average", "pca"):
        assert construction in restrictions["prohibited_constructions"], construction
    assert restrictions["both_channels_in_one_source_audit_table_allowed"] is True
    assert CONFIG["shared_price_stage_group"] == "io_sector_093_fuel_oil"


@requires_parquet
def test_the_table_keeps_the_channels_apart_by_key():
    rows = _table()
    assert {r["channel_id"] for r in rows} == {CH600, CH1500}
    for row in rows:
        assert bool(row["additive_aggregation_allowed"]) is False
        assert bool(row["simultaneous_model_entry_approved"]) is False
        assert row["shared_price_stage_group"] == "io_sector_093_fuel_oil"
    for month in ("2024-08", "2025-05"):
        values = {
            r["channel_id"]: r["feature_value"] for r in rows
            if r["reference_month"] == month and r["transformation_id"] == "price_level"
        }
        assert len(values) == 2
        assert values[CH600] != values[CH1500]


# ===========================================================================
# 12. C2 reconciliation
# ===========================================================================
def test_c8_uses_c2s_production_formula_implementation():
    from thai_supply_chain_ews.features import commodity_features as C2

    assert T.log_change_pct is C2.log_change_pct
    assert T.realized_volatility_pct is C2.realized_volatility_pct
    assert T.FEATURE_DEFINITIONS is C2.FEATURE_DEFINITIONS


def test_formula_compatibility_is_asserted_not_assumed():
    report = T.assert_c2_formula_compatibility()
    assert report["formula_compatible_with_c2"] is True
    assert report["natural_logarithm"] is True
    assert report["scaled_by_100"] is True
    assert report["volatility_ddof"] == 0
    assert report["volatility_required_price_levels"] == 4
    assert report["source_timing_contract_differs_from_c2"] is True
    assert report["input_lags"]["realized_volatility_3m_pct"] == [3, 2, 1, 0]


def test_a_divergent_c2_definition_would_raise(monkeypatch):
    monkeypatch.setitem(T.REQUIRED_INPUT_LAGS, "realized_volatility_3m_pct", (2, 1, 0))
    with pytest.raises(T.TransformationError, match="must not diverge"):
        T.assert_c2_formula_compatibility()


@requires_run
def test_timing_differences_from_c2_stay_explicit():
    reconciliation = _audit()["c2_reconciliation"]
    assert reconciliation["formula_compatible_with_c2"] is True
    assert reconciliation["source_timing_contract_differs_from_c2"] is True
    assert reconciliation["equivalent_timing_quality_implied"] is False
    differences = reconciliation["timing_differences"]
    assert differences["c2_values"] == "archived_first_release"
    assert differences["c8_values"] == "latest_vintage"
    assert differences["c2_publication_timing"] == "measured"
    assert differences["c8_operational_lag"] == "policy_based"
    assert differences["c2_point_in_time_supported"] is True
    assert differences["c8_point_in_time_supported"] is False
    assert reconciliation["divergent_logic_copied_into_c8"] is False


# ===========================================================================
# 13. Isolation
# ===========================================================================
FORBIDDEN_IMPORT_MODULES = {
    "matrices", "modeling", "evaluation", "targets", "structure", "build_panel",
    "industry_conditioning", "commodity_exposure", "sklearn", "joblib",
    "statsmodels",
}


def _imported_modules(source: str) -> set:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules.add(base)
            modules.update(f"{base}.{alias.name}".strip(".") for alias in node.names)
    return {segment for module in modules for segment in module.split(".")}


def test_c8_modules_import_no_exposure_target_or_model_code():
    package = ROOT / "src" / "thai_supply_chain_ews" / "features"
    for name in ("eppo_fuel_oil_transformations", "eppo_transformation_availability",
                 "eppo_transformation_lineage"):
        source = (package / f"{name}.py").read_text(encoding="utf-8")
        assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES), name


def test_the_runner_touches_no_exposure_target_or_locked_test_artifact():
    source = (ROOT / "scripts" / "run_c8_eppo_transformations.py").read_text(
        encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)
    for fragment in ("c3_commodity_exposure", "c4_wide_primary", "industry_month_panel",
                     "targets_table", "forecast_target", "production_stress",
                     "d1_development_predictions", "d3_operational_predictions",
                     "d4_operational_model_predictions", "b4_walk_forward",
                     "locked_test_predictions"):
        assert fragment not in source, fragment


@requires_run
def test_no_exposure_target_or_model_flag_is_true():
    audit = _audit()
    for key, value in audit["provenance"].items():
        assert value is False, key
    for key, value in audit["c9_boundary"].items():
        if isinstance(value, bool):
            assert value is False, key
    assert audit["feature_table"]["model_feature_approved_rows"] == 0


@requires_parquet
def test_the_table_has_no_exposure_or_target_column():
    rows = _table()
    for column in rows[0]:
        name = column.lower()
        for fragment in ("exposure", "industry", "mpi", "target", "prediction",
                         "residual", "stress"):
            assert fragment not in name, column


# ===========================================================================
# 14. Table shape and schema
# ===========================================================================
@requires_parquet
def test_feature_table_matches_its_schema():
    import pandas as pd

    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_source_transformation.schema.yaml").read_text(
            encoding="utf-8")
    )
    frame = pd.read_parquet(FEATURE_PARQUET)
    declared = [c["name"] for c in schema["observation"]["columns"]]
    assert set(declared) <= set(frame.columns)
    assert len(frame) == schema["grid"]["rows"] == 650
    assert not frame.duplicated(subset=schema["observation"]["grain"]).any()
    assert frame["source_available_as_of"].isna().all()
    assert (~frame["model_feature_approved"].astype(bool)).all()
    assert int(frame["feature_value"].notna().sum()) == schema["grid"]["finite_rows"]
    assert int(frame["feature_value"].isna().sum()) == schema["grid"]["null_rows"]


@requires_parquet
def test_feature_units_are_exact():
    rows = _table()
    for row in rows:
        assert row["feature_unit"] == T.TRANSFORMATION_UNITS[row["transformation_id"]]
    assert T.TRANSFORMATION_UNITS["price_level"] == "baht_per_litre"
    assert T.TRANSFORMATION_UNITS["log_change_1m_pct"] == "percentage_point_log_change"
    assert T.TRANSFORMATION_UNITS["realized_volatility_3m_pct"] == (
        "percentage_point_log_change_volatility"
    )


@requires_parquet
def test_the_table_ordering_is_deterministic():
    rows = _table()
    keys = [(r["channel_id"], r["reference_month"], r["transformation_id"])
            for r in rows]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


@requires_parquet
def test_values_reconstruct_from_the_c7_5_source_independently():
    import pandas as pd

    source = pd.read_parquet(SEMANTIC_PARQUET)
    prices = {
        (row["series_id"], row["reference_month"]): (
            None if pd.isna(row["monthly_value_strict"])
            else float(row["monthly_value_strict"])
        )
        for row in source.to_dict("records")
    }
    checked = 0
    for row in _table():
        if row["feature_value"] is None:
            continue
        window = [prices[(row["series_id"], m)] for m in row["required_input_months"]]
        transformation = row["transformation_id"]
        if transformation == "price_level":
            expected = window[0]
        elif transformation.startswith("log_change"):
            expected = 100.0 * (math.log(window[-1]) - math.log(window[0]))
        else:
            changes = [
                100.0 * (math.log(b) - math.log(a))
                for a, b in zip(window[:-1], window[1:], strict=True)
            ]
            mean = sum(changes) / len(changes)
            expected = math.sqrt(sum((c - mean) ** 2 for c in changes) / len(changes))
        assert row["feature_value"] == pytest.approx(expected, rel=1e-12), (
            row["channel_id"], row["reference_month"], transformation
        )
        checked += 1
    assert checked == 598


# ===========================================================================
# 15. Readiness
# ===========================================================================
@requires_run
def test_readiness_is_reported_per_channel_and_is_not_model_approval():
    readiness = _audit()["readiness"]
    assert set(readiness) == {CH600, CH1500}
    for channel, entry in readiness.items():
        assert entry["source_transformations_created"] is True
        assert entry["source_transformations_ready_for_structural_conditioning"] is True
        assert entry["industry_conditioned_features_created"] is False
        assert entry["feature_semantics_approved"] is False
        assert entry["model_feature_approved"] is False
        assert entry["rows"] == 325, channel
        assert entry["finite_rows"] == 299
        assert entry["null_rows"] == 26


@requires_run
def test_upstream_artifacts_are_unchanged():
    decision = json.loads(C7_5_DECISION.read_text(encoding="utf-8"))
    assert len(decision["monthly_rows"]) == 195
    assert decision["c8_authorization"]["c8_hsd_transformation_authorized"] is False
    assert _audit()["feature_table"]["output"] != (
        "data/interim/c7_5_eppo_monthly_semantic.parquet"
    )


# ===========================================================================
# 16. Synthetic failures. Each must raise explicitly.
# ===========================================================================
def test_synthetic_h_diesel_entering_the_source_table():
    with pytest.raises(T.UnauthorizedSeriesError):
        T.assert_strict_input(T.SourceMonth(
            series_id=HSD, reference_month="2023-05", monthly_value_strict=25.0,
            approved_transformation_input=True,
        ))
    with pytest.raises(T.UnauthorizedSeriesError):
        _grid(_source(series_id=HSD, months=6), series_ids=(HSD,), months=6)


def test_synthetic_descriptive_april_value_used_as_strict():
    # C7.5 publishes a descriptive 24-day mean for 2026-04; presenting it as an
    # approved strict input is the failure.
    smuggled = T.SourceMonth(
        series_id=FO600, reference_month="2026-04",
        monthly_value_strict=24.6477, approved_transformation_input=False,
    )
    with pytest.raises(T.TransformationError, match="not an approved"):
        T.assert_strict_input(smuggled)


def test_synthetic_missing_april_interpolated():
    values = {m: 10.0 for m in T.month_range("2021-01", "2026-05")}
    rows, _ = _grid(_source(values=values, gaps=("2026-04",)))
    april = _cell(rows, "2026-04", "price_level")
    assert april.feature_value is None
    with pytest.raises(LIN.EppoTransformationLineageError, match="partial input window"):
        LIN.transformation_lineage_record(
            transformation_id="price_level",
            transformation_formula_version=T.TRANSFORMATION_FORMULA_VERSION,
            channel_id=CH600, reference_month="2026-04",
            required_input_months=["2026-04"], available_inputs=[],
            missing_input_months=["2026-04"], feature_value=10.0,
            transformation_status="current_month_source_gap",
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
        )


def test_synthetic_may_change_calculated_despite_a_missing_april():
    rows, _ = _grid(_source(gaps=("2026-04",)))
    may = _cell(rows, "2026-05", "log_change_1m_pct")
    assert may.feature_value is None
    assert may.available_input_count == 1 and may.required_input_count == 2
    with pytest.raises(T.TransformationError, match="needs 2 price levels"):
        T.compute_transformation("log_change_1m_pct", [24.16])


def test_synthetic_volatility_declared_with_three_price_inputs():
    with pytest.raises(T.TransformationError, match="needs 4 price levels"):
        T.compute_transformation("realized_volatility_3m_pct", [10.0, 11.0, 12.0])
    with pytest.raises(LIN.EppoTransformationLineageError, match="does not account"):
        LIN.transformation_lineage_record(
            transformation_id="realized_volatility_3m_pct",
            transformation_formula_version=T.TRANSFORMATION_FORMULA_VERSION,
            channel_id=CH600, reference_month="2024-03",
            required_input_months=["2024-01", "2024-02", "2024-03"],
            available_inputs=[
                LIN.SourceInputLineage(FO600, m, 10.0)
                for m in ("2023-12", "2024-01", "2024-02", "2024-03")
            ],
            missing_input_months=[], feature_value=1.0,
            transformation_status="available_numeric",
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
        )


def test_synthetic_ddof_one_volatility():
    prices = [10.0, 11.0, 12.0, 12.5]
    changes = [
        100.0 * (math.log(b) - math.log(a))
        for a, b in zip(prices[:-1], prices[1:], strict=True)
    ]
    mean = sum(changes) / 3
    sample = math.sqrt(sum((c - mean) ** 2 for c in changes) / 2)
    produced = T.compute_transformation("realized_volatility_3m_pct", prices)
    assert produced != pytest.approx(sample)
    assert T.assert_c2_formula_compatibility()["volatility_ddof"] == 0


def test_synthetic_base_10_logarithm():
    produced = T.compute_transformation("log_change_1m_pct", [10.0, 20.0])
    assert produced != pytest.approx(100.0 * math.log10(2.0))
    assert produced == pytest.approx(100.0 * math.log(2.0))
    assert T.assert_c2_formula_compatibility()["natural_logarithm"] is True


def test_synthetic_fuel_oils_averaged():
    with pytest.raises(T.TransformationError, match="mutually exclusive"):
        T.assert_single_fuel_oil_channel(
            [CH600, CH1500], "mean of FO 600 and FO 1500"
        )


def test_synthetic_both_channels_requested_simultaneously():
    rows = [{
        "channel_id": CH600, "reference_month": "2024-01",
        "policy_available_month": "2024-03", "feature_value": 1.0,
        "transformation_status": "available_numeric", "source_available_as_of": None,
        "operational_lag_is_measured": False,
        "availability_basis": AV.AVAILABILITY_BASIS,
    }]
    with pytest.raises(T.TransformationError, match="mutually exclusive"):
        AV.select_source_transformations_available_at_issue(
            rows, "2024-06", [CH600, CH1500]
        )


def test_synthetic_lag_2_described_as_measured():
    with pytest.raises(AV.AvailabilityPolicyError, match="conservative project policy"):
        AV.assert_policy_month_is_not_a_release_date({
            "source_available_as_of": None, "operational_lag_is_measured": True,
            "availability_basis": AV.AVAILABILITY_BASIS,
        })


def test_synthetic_policy_date_stored_as_a_source_release_date():
    with pytest.raises(AV.AvailabilityPolicyError, match="not a release date"):
        AV.assert_policy_month_is_not_a_release_date({
            "channel_id": CH600, "reference_month": "2024-01",
            "transformation_id": "price_level",
            "source_available_as_of": "2024-03-01",
        })


@requires_parquet
def test_synthetic_null_grid_rows_dropped():
    rows = _table()
    assert len(rows) == 650
    kept = [r for r in rows if r["feature_value"] is None]
    assert len(kept) == 52
    # Dropping them would leave a table that still looks complete.
    dropped = [r for r in rows if r["feature_value"] is not None]
    assert len(dropped) == 598
    assert len(dropped) != len(rows)
    for row in kept:
        assert row["transformation_status"] != "available_numeric"
        assert row["missing_input_months"]


def test_synthetic_target_outcome_used_for_channel_selection():
    assert CONFIG["channel_restrictions"][
        "outcome_based_channel_selection_allowed"] is False
    assert CONFIG["authorizations"][
        "c8_outcome_based_channel_selection_authorized"] is False
    with pytest.raises(T.TransformationError, match="mutually exclusive"):
        T.assert_single_fuel_oil_channel(
            [CH600, CH1500], "keep whichever channel has the lower development MAE"
        )


def test_synthetic_industry_exposure_coefficient_applied_in_c8():
    package = ROOT / "src" / "thai_supply_chain_ews" / "features"
    for name in ("eppo_fuel_oil_transformations", "eppo_transformation_availability",
                 "eppo_transformation_lineage"):
        source = (package / f"{name}.py").read_text(encoding="utf-8")
        assert "commodity_exposure" not in source, name
        assert not (_imported_modules(source) & {"matrices", "commodity_exposure"}), name
    assert CONFIG["authorizations"]["c8_industry_conditioning_authorized"] is False
    assert CONFIG["readiness"]["industry_conditioned_features_created"] is False
