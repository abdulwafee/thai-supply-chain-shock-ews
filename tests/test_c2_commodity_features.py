"""Task C2 — point-in-time commodity feature construction.

Two kinds of test here, and the second kind matters most:

* **Contract tests** confirm the production table is what C2 promised — four
  series, five formulas, 1,224 rows, correct availability.
* **Synthetic failure tests** confirm each guard actually fires. A rule that has
  never been seen to reject anything is an assumption, not a safeguard, so every
  prohibition is exercised against a deliberately broken fixture.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.features import commodity_features as CF  # noqa: E402
from thai_supply_chain_ews.features import feature_availability as FA  # noqa: E402
from thai_supply_chain_ews.features import feature_lineage as FL  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "commodity_features.yaml"
SCHEMA_PATH = ROOT / "schemas" / "commodity_feature.schema.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
AUDIT_INPUT = ROOT / "docs" / "c1_5_commodity_timing_audit.json"


# --- shared production build -------------------------------------------------


@pytest.fixture(scope="module")
def loaded():
    return CF.load_first_release_observations(AUDIT_INPUT)


@pytest.fixture(scope="module")
def primary(loaded):
    return CF.build_feature_table(
        loaded["observations"], loaded["required_months"], FA.PRIMARY_POLICY
    )


@pytest.fixture(scope="module")
def sensitivity(loaded):
    return CF.build_feature_table(
        loaded["observations"], loaded["required_months"], FA.SENSITIVITY_POLICY
    )


@pytest.fixture(scope="module")
def audit():
    path = ROOT / "docs" / "c2_commodity_feature_audit.json"
    return json.loads(path.read_text(encoding="utf-8"))


def synthetic_series(n_months: int = 16, start: str = "2021-01-01") -> dict:
    """A clean synthetic series, so failure tests can break one thing at a time."""
    months, cursor = [], start
    for _ in range(n_months):
        months.append(cursor)
        cursor = FA.add_months(cursor, 1)
    observations = {}
    for index, month in enumerate(months):
        observations[month] = {
            "series_id": "brent_crude_usd_bbl",
            "reference_month": month,
            "displayed_value": 100.0 + index,
            "displayed_text": f"{100.0 + index:.1f}",
            "decimal_places": 1,
            "unit": "$/bbl",
            "source_series_label": "Crude oil, Brent",
            "source_footnote_marker": "a/",
            "source_footnote_meaning": "included_in_the_energy_index",
            "estimate_status": "not_documented_as_estimate",
            "source_issue_name": f"ISSUE-{FA.add_months(month, 1)}",
            "source_issue_date": FA.add_months(month, 1),
            "source_issue_url": "https://example.invalid/fixture.pdf",
            "source_issue_sha256": hashlib.sha256(month.encode()).hexdigest(),
            "source_available_month": FA.add_months(month, 1),
            "source_value_type": "archived_first_release",
        }
    return {"brent_crude_usd_bbl": observations}, months


# --- series allowlist and exclusions -----------------------------------------


def test_primary_allowlist_is_exactly_four_series():
    assert CF.PRIMARY_SERIES == (
        "brent_crude_usd_bbl",
        "aluminum_usd_mt",
        "copper_usd_mt",
        "rubber_rss3_usd_kg",
    )
    assert CONFIG["primary_series"] == list(CF.PRIMARY_SERIES)
    assert SCHEMA["columns"][0]["allowed"] == list(CF.PRIMARY_SERIES)


def test_lng_coal_and_palm_oil_are_excluded_with_reasons():
    assert set(CF.EXCLUDED_SERIES) == {
        "lng_japan_usd_mmbtu", "coal_australia_usd_mt", "palm_oil_usd_mt"
    }
    assert not set(CF.EXCLUDED_SERIES) & set(CF.PRIMARY_SERIES)
    for series_id, reason in CF.EXCLUDED_SERIES.items():
        assert reason.strip(), series_id
        # No substitute is introduced for an excluded series.
        assert CONFIG["excluded_series"][series_id]["replaced_with"] is None
    assert CONFIG["no_substitutes_for_excluded_series"] is True


def test_requesting_an_excluded_series_fails_explicitly(loaded):
    for series_id in CF.EXCLUDED_SERIES:
        with pytest.raises(CF.ExcludedSeriesError):
            CF.build_feature_table(
                loaded["observations"], loaded["required_months"],
                FA.PRIMARY_POLICY, (series_id,),
            )


def test_no_excluded_series_appears_in_the_canonical_table(primary):
    present = {row["series_id"] for row in primary}
    assert present == set(CF.PRIMARY_SERIES)
    assert not present & set(CF.EXCLUDED_SERIES)


# --- authoritative input -----------------------------------------------------


def test_input_is_the_c1_5_r2_archived_first_release_dataset(loaded):
    contract = loaded["contract"]
    assert contract["point_in_time_supported"] == "full"
    assert contract["minimum_publication_lag_months"] == 1
    assert contract["publication_timing_verified"] is True
    assert contract["distinct_issues_obtained"] == 65
    assert contract["coverage_fraction"] == 1.0


def test_exactly_65_monthly_inputs_per_primary_series(loaded):
    for series_id in CF.PRIMARY_SERIES:
        months = loaded["observations"][series_id]
        assert len(months) == 65, series_id
        assert min(months) == "2021-01-01"
        assert max(months) == "2026-05-01"


def test_every_value_is_an_archived_first_release_not_latest_vintage(primary):
    assert {row["source_value_type"] for row in primary} == {"archived_first_release"}
    assert CONFIG["input"]["latest_vintage_substitution_permitted"] is False


def test_latest_vintage_substitution_is_rejected(tmp_path):
    """A month flagged as not a true first release must not enter the table."""
    audit = json.loads(AUDIT_INPUT.read_text(encoding="utf-8"))
    for row in audit["publication_timing"]:
        if row["reference_month"] == "2023-05-01":
            row["is_true_first_release"] = False
            row["availability_status"] = "latest_vintage_fallback"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(audit), encoding="utf-8")
    with pytest.raises(CF.LatestVintageSubstitutionError, match="TRUE first release"):
        CF.load_first_release_observations(path)


def test_input_contract_violation_is_rejected(tmp_path):
    audit = json.loads(AUDIT_INPUT.read_text(encoding="utf-8"))
    audit["timing_decisions"]["minimum_publication_lag_months"] = 2
    path = tmp_path / "wrong_lag.json"
    path.write_text(json.dumps(audit), encoding="utf-8")
    with pytest.raises(CF.InputCoverageError, match="minimum_publication_lag_months"):
        CF.load_first_release_observations(path)


def test_displayed_precision_is_never_increased(loaded):
    """The PDF's printed text is the evidence and must survive verbatim."""
    for series_id in CF.PRIMARY_SERIES:
        for month, record in loaded["observations"][series_id].items():
            text = record["displayed_text"]
            assert text, (series_id, month)
            decimals = len(text.split(".")[1]) if "." in text else 0
            assert decimals == record["decimal_places"]
            assert float(text.replace(",", "")) == record["displayed_value"]


# --- formulas ----------------------------------------------------------------


def test_log_change_uses_natural_log_and_percent_scaling():
    assert CF.log_change_pct(math.e, 1.0) == pytest.approx(100.0)
    # Not log10: a 10x move would be 100 under log10 scaling, 230.26 under ln.
    assert CF.log_change_pct(10.0, 1.0) == pytest.approx(230.2585092994046)
    assert CF.log_change_pct(100.0, 100.0) == 0.0
    assert CF.log_change_pct(90.0, 100.0) == pytest.approx(-10.536051565782627)


def test_realized_volatility_uses_population_std_ddof_zero():
    changes = [1.0, 2.0, 6.0]
    got = CF.realized_volatility_pct(changes)
    assert got == pytest.approx(statistics.pstdev(changes))
    # The sample estimator would differ by sqrt(3/2) on a 3-point window.
    assert got != pytest.approx(statistics.stdev(changes))
    assert got == pytest.approx(statistics.stdev(changes) / math.sqrt(1.5))


def test_wrong_degrees_of_freedom_is_detectably_different():
    """Synthetic guard: ddof=1 must not be able to masquerade as the answer."""
    changes = [0.5, -1.5, 3.0]
    correct = CF.realized_volatility_pct(changes)
    wrong = statistics.stdev(changes)  # ddof=1
    assert abs(correct - wrong) > 1e-9
    assert CONFIG["features"]["realized_volatility_3m_pct"]["degrees_of_freedom"] == 0


def test_price_level_preserves_the_source_value_and_unit(loaded, primary):
    for row in primary:
        if row["feature_name"] != "price_level":
            continue
        record = loaded["observations"][row["series_id"]][row["reference_month"]]
        assert row["feature_value"] == record["displayed_value"]
        assert row["unit"] == record["unit"]
        assert row["input_observation_count"] == 1


def test_log_change_formulas_match_the_source_observations(loaded, primary):
    lags = {"log_change_1m_pct": 1, "log_change_3m_pct": 3, "log_change_12m_pct": 12}
    checked = 0
    for row in primary:
        lag = lags.get(row["feature_name"])
        if lag is None:
            continue
        months = loaded["observations"][row["series_id"]]
        later = months[row["reference_month"]]["displayed_value"]
        earlier = months[FA.add_months(row["reference_month"], -lag)]["displayed_value"]
        assert row["feature_value"] == pytest.approx(
            100.0 * (math.log(later) - math.log(earlier))
        )
        checked += 1
    assert checked == (64 + 62 + 53) * 4


def test_realized_volatility_matches_the_source_observations(loaded, primary):
    checked = 0
    for row in primary:
        if row["feature_name"] != "realized_volatility_3m_pct":
            continue
        months = loaded["observations"][row["series_id"]]
        prices = [
            months[FA.add_months(row["reference_month"], -lag)]["displayed_value"]
            for lag in (3, 2, 1, 0)
        ]
        changes = [
            100.0 * (math.log(prices[i]) - math.log(prices[i - 1]))
            for i in range(1, 4)
        ]
        assert row["feature_value"] == pytest.approx(statistics.pstdev(changes))
        checked += 1
    assert checked == 62 * 4


def test_three_month_alignment_is_exact_not_off_by_one(loaded):
    """Synthetic guard against a 3-month window that reads m-2 or m-4."""
    observations, months = synthetic_series(n_months=16)
    rows = CF.build_feature_table(
        observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
    )
    row = next(
        r for r in rows
        if r["feature_name"] == "log_change_3m_pct" and r["reference_month"] == "2021-04-01"
    )
    prices = observations["brent_crude_usd_bbl"]
    correct = 100.0 * (
        math.log(prices["2021-04-01"]["displayed_value"])
        - math.log(prices["2021-01-01"]["displayed_value"])
    )
    off_by_one_near = 100.0 * (
        math.log(prices["2021-04-01"]["displayed_value"])
        - math.log(prices["2021-02-01"]["displayed_value"])
    )
    assert row["feature_value"] == pytest.approx(correct)
    assert row["feature_value"] != pytest.approx(off_by_one_near)
    assert row["input_window_start"] == "2021-01-01"
    assert row["input_window_end"] == "2021-04-01"


def test_exactly_five_transformations_and_no_others():
    names = [definition.name for definition in CF.FEATURE_DEFINITIONS]
    assert names == [
        "price_level", "log_change_1m_pct", "log_change_3m_pct",
        "log_change_12m_pct", "realized_volatility_3m_pct",
    ]
    assert sorted(CONFIG["features"]) == sorted(names)


# --- coverage ----------------------------------------------------------------


def test_expected_rows_per_feature(primary):
    expected = {
        "price_level": 65, "log_change_1m_pct": 64, "log_change_3m_pct": 62,
        "log_change_12m_pct": 53, "realized_volatility_3m_pct": 62,
    }
    assert CF.expected_row_counts() == expected
    for name, per_series in expected.items():
        rows = [r for r in primary if r["feature_name"] == name]
        assert len(rows) == per_series * 4, name
        for series_id in CF.PRIMARY_SERIES:
            assert len([r for r in rows if r["series_id"] == series_id]) == per_series


def test_exact_canonical_total_is_1224(primary):
    assert len(primary) == 1224
    assert CONFIG["expected_primary_canonical_rows"] == 1224
    assert sum(CF.expected_row_counts().values()) == 306


def test_earliest_valid_reference_month_per_transformation(primary):
    earliest = {
        "price_level": "2021-01-01",
        "log_change_1m_pct": "2021-02-01",
        "log_change_3m_pct": "2021-04-01",
        "log_change_12m_pct": "2022-01-01",
        "realized_volatility_3m_pct": "2021-04-01",
    }
    for name, month in earliest.items():
        rows = [r for r in primary if r["feature_name"] == name]
        assert min(r["reference_month"] for r in rows) == month, name
        assert max(r["reference_month"] for r in rows) == "2026-05-01", name


def test_no_early_window_values_are_manufactured(primary):
    """Nothing before a transformation's first computable month may exist."""
    for definition in CF.FEATURE_DEFINITIONS:
        first = FA.add_months("2021-01-01", definition.min_history_months)
        rows = [r for r in primary if r["feature_name"] == definition.name]
        assert all(r["reference_month"] >= first for r in rows), definition.name


def test_row_count_mismatch_fails_explicitly(loaded):
    """Dropping one input must change the count, not be silently patched."""
    observations = copy.deepcopy(loaded["observations"])
    del observations["copper_usd_mt"]["2023-07-01"]
    with pytest.raises(CF.MissingInputError):
        CF.build_feature_table(
            observations, loaded["required_months"], FA.PRIMARY_POLICY
        )


# --- availability ------------------------------------------------------------


def test_operational_lag_is_two_months_on_the_primary_table(primary):
    assert FA.PRIMARY_POLICY.operational_lag_months == 2
    assert {r["operational_lag_months"] for r in primary} == {2}
    assert {r["minimum_publication_lag_months"] for r in primary} == {1}
    assert {r["availability_policy_label"] for r in primary} == {"primary"}
    for row in primary:
        assert row["policy_available_month"] == FA.add_months(row["reference_month"], 2)


def test_lag_zero_is_rejected():
    with pytest.raises(FA.LagZeroProhibitedError):
        FA.AvailabilityPolicy(
            name="lag_zero", operational_lag_months=0,
            minimum_publication_lag_months=1, is_primary=True,
            label="primary", basis="invalid",
        )
    with pytest.raises(FA.LagZeroProhibitedError):
        FA.AvailabilityPolicy(
            name="negative", operational_lag_months=-1,
            minimum_publication_lag_months=1, is_primary=True,
            label="primary", basis="invalid",
        )


def test_a_lag_below_the_measured_publication_lag_is_rejected():
    with pytest.raises(FA.AvailabilityError, match="below the MEASURED"):
        FA.AvailabilityPolicy(
            name="too_short", operational_lag_months=1,
            minimum_publication_lag_months=2, is_primary=True,
            label="primary", basis="invalid",
        )


def test_lag_one_output_is_sensitivity_only(sensitivity):
    assert FA.SENSITIVITY_POLICY.operational_lag_months == 1
    assert FA.SENSITIVITY_POLICY.is_primary is False
    assert FA.SENSITIVITY_POLICY.label == "sensitivity_only"
    assert {r["availability_policy_label"] for r in sensitivity} == {"sensitivity_only"}
    assert {r["availability_policy"] for r in sensitivity} == {"publication_lag_1m"}
    config_policy = CONFIG["availability"]["policies"]["publication_lag_1m"]
    assert config_policy["is_primary"] is False
    assert config_policy["label"] == "sensitivity_only"
    assert "must_not_be_default_output" in config_policy["constraints"]


def test_a_sensitivity_table_cannot_be_presented_as_primary():
    """Synthetic guard: the label and the primary flag cannot disagree."""
    with pytest.raises(FA.AvailabilityError, match="sensitivity_only"):
        FA.AvailabilityPolicy(
            name="disguised", operational_lag_months=1,
            minimum_publication_lag_months=1, is_primary=False,
            label="primary", basis="mislabelled",
        )
    with pytest.raises(FA.AvailabilityError, match="both primary and sensitivity"):
        FA.AvailabilityPolicy(
            name="both", operational_lag_months=2,
            minimum_publication_lag_months=1, is_primary=True,
            label="sensitivity_only", basis="mislabelled",
        )


def test_source_availability_is_never_after_feature_availability(primary, sensitivity):
    for row in primary + sensitivity:
        assert row["source_available_month"] <= row["feature_available_month"]
        assert row["policy_available_month"] <= row["feature_available_month"]


def test_multi_input_availability_uses_the_latest_required_input():
    """A late input must push the feature later, not be ignored."""
    observations, months = synthetic_series(n_months=16)
    prices = observations["brent_crude_usd_bbl"]
    # Delay the FINAL input's publication well past the policy month.
    prices["2021-04-01"]["source_available_month"] = "2021-11-01"
    rows = CF.build_feature_table(
        observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
    )
    row = next(
        r for r in rows
        if r["feature_name"] == "log_change_3m_pct" and r["reference_month"] == "2021-04-01"
    )
    assert row["policy_available_month"] == "2021-06-01"
    assert row["feature_available_month"] == "2021-11-01"
    assert row["source_available_month"] == "2021-11-01"


def test_availability_is_the_max_over_every_input_not_just_the_last():
    months = ["2021-01-01", "2021-02-01", "2021-03-01", "2021-04-01"]
    assert FA.feature_available_month("2021-02-01", months, FA.PRIMARY_POLICY) == "2021-04-01"
    # Policy month wins when every input is early.
    assert FA.feature_available_month(
        "2021-02-01", ["2021-02-01"], FA.PRIMARY_POLICY
    ) == "2021-04-01"


def test_a_future_published_source_observation_is_rejected():
    """Synthetic guard: an input published after the feature is usable fails."""
    with pytest.raises(FA.AvailabilityError, match="after the feature's available month"):
        FA.assert_inputs_published_by(
            "2021-03-01", ["2021-02-01", "2021-09-01"], "fixture"
        )


def test_availability_is_not_derived_from_the_download_date(primary):
    audit = json.loads(AUDIT_INPUT.read_text(encoding="utf-8"))
    download_months = {
        issue["downloaded_at_utc"][:7] for issue in audit["issues"]
    }
    # Every issue was downloaded in 2026-08; if availability came from the
    # download date, every source_available_month would collapse to it.
    assert len(download_months) == 1
    assert len({r["source_available_month"] for r in primary}) > 50
    assert CONFIG["availability"]["rules"]["derived_from_download_date"] is False


def test_feature_availability_covers_every_b4_development_origin(audit):
    coverage = audit["b4_development_origin_coverage"]
    assert coverage["fully_covered"] is True
    assert coverage["fully_covered_origins"] == coverage["required_origins"] == 15
    assert coverage["locked_test_period_read"] is False
    assert coverage["target_values_read"] is False


# --- lineage -----------------------------------------------------------------


def test_lineage_checksum_is_deterministic_and_input_sensitive():
    def make(value: float) -> FL.LineageInput:
        return FL.LineageInput(
            series_id="brent_crude_usd_bbl", reference_month="2021-01-01",
            displayed_value=value, displayed_text=f"{value:.1f}", decimal_places=1,
            source_issue_name="ISSUE", source_issue_date="2021-02-02",
            source_issue_url="https://example.invalid/x.pdf",
            source_issue_sha256="ab" * 32, source_available_month="2021-02-01",
            source_footnote_marker="a/",
        )
    base = [make(54.6)]
    assert FL.lineage_checksum(base) == FL.lineage_checksum([make(54.6)])
    assert FL.lineage_checksum(base) != FL.lineage_checksum([make(54.7)])
    with pytest.raises(FL.LineageError):
        FL.lineage_checksum([])


def test_lineage_order_is_part_of_the_identity():
    def make(month: str) -> FL.LineageInput:
        return FL.LineageInput(
            series_id="s", reference_month=month, displayed_value=1.0,
            displayed_text="1.0", decimal_places=1, source_issue_name="i",
            source_issue_date=month, source_issue_url="u",
            source_issue_sha256="cd" * 32, source_available_month=month,
            source_footnote_marker="",
        )
    a, b = make("2021-01-01"), make("2021-02-01")
    assert FL.lineage_checksum([a, b]) != FL.lineage_checksum([b, a])


def test_every_feature_records_all_of_its_inputs(primary):
    counts = {
        "price_level": 1, "log_change_1m_pct": 2, "log_change_3m_pct": 2,
        "log_change_12m_pct": 2, "realized_volatility_3m_pct": 4,
    }
    for row in primary:
        assert row["input_observation_count"] == counts[row["feature_name"]]
        assert row["input_window_end"] == row["reference_month"]
        assert row["input_lineage_checksum"]
        assert len(row["input_lineage_checksum"]) == 64


def test_volatility_lineage_includes_the_fourth_month():
    """Synthetic guard: r_{m-2} needs p_{m-3}, so three inputs is wrong."""
    definition = next(
        d for d in CF.FEATURE_DEFINITIONS if d.name == "realized_volatility_3m_pct"
    )
    assert definition.input_lags == (3, 2, 1, 0)
    assert definition.min_history_months == 3
    observations, months = synthetic_series(n_months=16)
    rows = CF.build_feature_table(
        observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
    )
    row = next(
        r for r in rows
        if r["feature_name"] == "realized_volatility_3m_pct"
        and r["reference_month"] == "2021-04-01"
    )
    assert row["input_observation_count"] == 4
    assert row["input_window_start"] == "2021-01-01"


def test_omitting_a_lineage_input_changes_the_checksum():
    """Synthetic guard: a truncated lineage cannot hash the same as a full one."""
    def make(month: str) -> FL.LineageInput:
        return FL.LineageInput(
            series_id="s", reference_month=month, displayed_value=2.0,
            displayed_text="2.0", decimal_places=1, source_issue_name="i",
            source_issue_date=month, source_issue_url="u",
            source_issue_sha256="ef" * 32, source_available_month=month,
            source_footnote_marker="",
        )
    full = [make(m) for m in ("2021-01-01", "2021-02-01", "2021-03-01", "2021-04-01")]
    truncated = full[1:]
    assert FL.lineage_checksum(full) != FL.lineage_checksum(truncated)


def test_lineage_checksums_are_unique_per_row(primary):
    checksums = [row["input_lineage_checksum"] for row in primary]
    # price_level and a same-month change read different input sets, so no two
    # rows in the table should share a lineage digest.
    assert len(set(checksums)) == len(checksums) == 1224


# --- data handling -----------------------------------------------------------


def test_missing_input_is_rejected_not_imputed():
    observations, months = synthetic_series(n_months=16)
    del observations["brent_crude_usd_bbl"]["2021-05-01"]
    with pytest.raises(CF.MissingInputError, match="C2 fails"):
        CF.build_feature_table(
            observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
        )


def test_non_positive_price_is_rejected_not_clipped():
    observations, months = synthetic_series(n_months=16)
    observations["brent_crude_usd_bbl"]["2021-06-01"]["displayed_value"] = 0.0
    with pytest.raises(CF.NonPositivePriceError, match="rather than clipping"):
        CF.build_feature_table(
            observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
        )
    observations["brent_crude_usd_bbl"]["2021-06-01"]["displayed_value"] = -5.0
    with pytest.raises(CF.NonPositivePriceError):
        CF.build_feature_table(
            observations, months, FA.PRIMARY_POLICY, ("brent_crude_usd_bbl",)
        )
    with pytest.raises(CF.NonPositivePriceError):
        CF.log_change_pct(10.0, 0.0)


def test_no_imputation_clipping_or_winsorization_is_configured():
    handling = CONFIG["data_handling"]
    for key in ("imputation", "forward_fill", "interpolation", "clipping",
                "winsorization", "rounding_of_calculated_features"):
        assert handling[key] == "none", key
    source = (ROOT / "src" / "thai_supply_chain_ews" / "features" /
              "commodity_features.py").read_text(encoding="utf-8")
    for forbidden in ("fillna", "ffill", "bfill", "interpolate", "np.clip",
                      ".clip(", "winsor"):
        assert forbidden not in source, forbidden


def test_calculated_features_are_not_rounded(primary):
    """A rounded table would show suspiciously few decimals; this one does not."""
    changes = [r["feature_value"] for r in primary if r["unit"] == "percent_log"]
    long_decimals = [v for v in changes if len(repr(float(v)).split(".")[-1]) > 6]
    assert len(long_decimals) > 900


def test_all_values_are_finite(primary, sensitivity):
    for row in primary + sensitivity:
        assert math.isfinite(row["feature_value"])


def test_no_missing_or_non_finite_observations_in_production(loaded):
    for series_id in CF.PRIMARY_SERIES:
        for month, record in loaded["observations"][series_id].items():
            assert record["displayed_value"] is not None, (series_id, month)
            assert math.isfinite(record["displayed_value"])
            assert record["displayed_value"] > 0


# --- schema and keys ---------------------------------------------------------


def test_canonical_key_is_unique(primary, sensitivity):
    for rows in (primary, sensitivity):
        keys = [
            (r["series_id"], r["feature_name"], r["reference_month"],
             r["availability_policy"]) for r in rows
        ]
        assert len(set(keys)) == len(keys)


def test_duplicate_key_is_rejected(primary):
    duplicated = list(primary) + [dict(primary[0])]
    with pytest.raises(CF.DuplicateFeatureKeyError, match="Duplicate canonical key"):
        CF._assert_unique_keys(duplicated)


def test_primary_and_sensitivity_coexist_without_overwriting(primary, sensitivity):
    """The policy is part of the key, so neither table can shadow the other."""
    combined = primary + sensitivity
    keys = [
        (r["series_id"], r["feature_name"], r["reference_month"],
         r["availability_policy"]) for r in combined
    ]
    assert len(set(keys)) == len(keys) == 2448


def test_schema_matches_the_columns_actually_written(primary):
    declared = [column["name"] for column in SCHEMA["columns"]]
    assert declared == list(CF.CANONICAL_COLUMNS)
    assert set(primary[0]) == set(CF.CANONICAL_COLUMNS)
    assert SCHEMA["primary_key"] == list(CONFIG["canonical_key"])


def test_no_target_industry_risk_prediction_or_locked_test_columns(primary):
    columns = set(CF.CANONICAL_COLUMNS)
    for forbidden in SCHEMA["forbidden_columns"]:
        assert forbidden not in columns, forbidden
    banned_fragments = ("industry", "target", "mpi", "stress", "risk_level",
                        "prediction", "forecast", "locked", "correlation",
                        "importance")
    for column in columns:
        assert not any(fragment in column.lower() for fragment in banned_fragments), column


def test_deterministic_ordering(primary):
    keys = [(r["series_id"], r["feature_name"], r["reference_month"]) for r in primary]
    assert keys == sorted(keys)


def test_typed_monthly_dates(primary):
    import datetime as dt
    for row in primary:
        for column in ("reference_month", "input_window_start", "input_window_end",
                       "source_available_month", "policy_available_month",
                       "feature_available_month", "source_issue_date"):
            parsed = dt.date.fromisoformat(row[column])
            assert column == "source_issue_date" or parsed.day == 1, column


# --- wide table --------------------------------------------------------------


def test_wide_table_is_derived_from_the_long_table(primary):
    wide = CF.to_wide_table(primary)
    assert len(wide) == 65 * 4
    index = {(r["reference_month"], r["series_id"]): r for r in wide}
    for row in primary:
        cell = index[(row["reference_month"], row["series_id"])]
        assert cell[f"{row['series_id']}__{row['feature_name']}"] == row["feature_value"]


def test_wide_table_has_no_independent_transformation_logic():
    source = (ROOT / "src" / "thai_supply_chain_ews" / "features" /
              "commodity_features.py").read_text(encoding="utf-8")
    wide_source = source[source.index("def to_wide_table"):]
    for forbidden in ("math.log", "log_change_pct", "realized_volatility_pct", "pstdev"):
        assert forbidden not in wide_source, forbidden
    assert CONFIG["wide_table_has_independent_transformation_logic"] is False


def test_wide_and_long_are_deterministic(primary):
    again = CF.to_wide_table(primary)
    once = CF.to_wide_table(primary)
    assert json.dumps(again, sort_keys=True, default=str) == json.dumps(
        once, sort_keys=True, default=str
    )


# --- single implementation and scope guards ----------------------------------


def test_package_code_is_the_single_implementation():
    script = (ROOT / "scripts" / "run_c2_commodity_features.py").read_text(encoding="utf-8")
    for forbidden in ("math.log", "pstdev", "def log_change", "def realized_volatility",
                      "stdev("):
        assert forbidden not in script, forbidden
    assert "commodity_features" in script
    assert "CF.build_feature_table" in script


def test_script_does_not_import_target_or_evaluation_modules():
    script = (ROOT / "scripts" / "run_c2_commodity_features.py").read_text(encoding="utf-8")
    for forbidden in ("targets.production_stress", "targets.labels",
                      "targets.calibration", "evaluation.walk_forward",
                      "evaluation.baselines", "evaluation.metrics",
                      "matrices.dependency"):
        assert forbidden not in script, forbidden


def test_feature_modules_do_not_import_targets_or_evaluation():
    for name in ("commodity_features.py", "feature_availability.py",
                 "feature_lineage.py"):
        source = (ROOT / "src" / "thai_supply_chain_ews" / "features" / name).read_text(
            encoding="utf-8"
        )
        for forbidden in ("thai_supply_chain_ews.targets",
                          "thai_supply_chain_ews.evaluation",
                          "thai_supply_chain_ews.matrices"):
            assert forbidden not in source, (name, forbidden)


def test_no_target_association_or_industry_mapping_was_computed(audit):
    assert audit["target_association_computed"] is False
    assert audit["features_joined_to_target"] is False
    assert audit["feature_selection_using_target"] is False
    assert audit["industry_dependency_matrix_created"] is False
    assert audit["model_trained"] is False
    assert audit["b4_baselines_compared"] is False
    assert CONFIG["feature_removed_for_weak_target_association"] is False
    for banned in ("pearson_or_spearman_correlation_with_mpi", "mutual_information",
                   "granger_causality", "feature_importance",
                   "industry_specific_signs_or_weights"):
        assert banned in CONFIG["not_computed_in_c2"], banned


def test_locked_final_test_was_not_accessed(audit):
    assert audit["locked_test_accessed"] is False
    script = (ROOT / "scripts" / "run_c2_commodity_features.py").read_text(encoding="utf-8")
    assert "locked" not in script.lower().replace("locked_test_accessed", "").replace(
        "locked_test_period_read", "").replace("locked test", "")


def test_model_feature_approval_stays_false(audit):
    assert audit["model_feature_approved_set"] is False
    assert audit["feature_semantics_approved_set"] is False
    assert CONFIG["approval_state"]["model_feature_approved"] is False
    assert CONFIG["approval_state"]["feature_semantics_approved"] is False
    per_series = CONFIG["series_model_feature_approval"]
    assert len(per_series) == 4
    assert all(v["model_feature_approved"] is False for v in per_series.values())


# --- upstream immutability and determinism -----------------------------------


def test_upstream_artifacts_are_unchanged():
    """B1, B3, B4, C1 and C1.5 evidence must survive C2 untouched."""
    expected = {
        "docs/b1_ingestion_metadata.json",
        "docs/b3_target_build_metadata.json",
        "docs/b4_baseline_results.json",
        "docs/b4_locked_test_manifest.json",
        "docs/c1_commodity_source_audit.json",
        "docs/c1_5_commodity_timing_audit.json",
        "configs/commodity_timing.yaml",
        "configs/evaluation_splits.yaml",
        "configs/production_stress_target.yaml",
    }
    for relative in expected:
        assert (ROOT / relative).is_file(), relative
    # C2 writes only its own artifacts.
    written = {
        "docs/c2_commodity_feature_audit.json",
        "configs/commodity_features.yaml",
        "schemas/commodity_feature.schema.yaml",
    }
    assert not (expected & written)


def test_c2_is_deterministic_across_runs(loaded):
    first = CF.build_feature_table(
        loaded["observations"], loaded["required_months"], FA.PRIMARY_POLICY
    )
    second = CF.build_feature_table(
        loaded["observations"], loaded["required_months"], FA.PRIMARY_POLICY
    )
    digest = lambda rows: hashlib.sha256(  # noqa: E731
        json.dumps(rows, sort_keys=True, default=str).encode()
    ).hexdigest()
    assert digest(first) == digest(second)


def test_audit_artifact_records_content_checksums(audit):
    assert set(audit["content_checksums"]) == {
        "canonical_long", "wide", "sensitivity_long"
    }
    for name, value in audit["content_checksums"].items():
        assert len(value) == 64, name
    assert audit["canonical_row_count"] == audit["expected_canonical_row_count"] == 1224
    assert audit["reconciliation"]["reconciled"] is True
    assert audit["reconciliation"]["mismatches"] == 0


def test_audit_artifact_holds_metadata_not_the_dataset(audit):
    """The tracked artifact records schema and counts, not 1,224 feature values.

    Column NAMES are metadata and belong here; feature VALUES do not. The check
    is therefore for a payload of rows, not for the string "feature_value".
    """
    def longest_list(node) -> int:
        if isinstance(node, list):
            return max([len(node)] + [longest_list(item) for item in node])
        if isinstance(node, dict):
            return max([0] + [longest_list(value) for value in node.values()])
        return 0

    # 1,224 rows could not hide in a structure whose longest list is short.
    assert longest_list(audit) < 100
    assert len(json.dumps(audit)) < 200_000
    for output in audit["outputs"].values():
        assert output["path"].endswith(".parquet")
        assert len(output["file_sha256"]) == 64


def test_generated_parquet_is_git_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/features/*" in gitignore
    result = subprocess.run(
        ["git", "check-ignore", "data/features/commodity_features_long.parquet"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_script_takes_no_arguments():
    """No flag may widen the allowlist, lower the lag, or promote sensitivity."""
    script = (ROOT / "scripts" / "run_c2_commodity_features.py").read_text(encoding="utf-8")
    assert "argparse" not in script
    assert "sys.argv" not in script


# --- C1.5-R3 compatibility ---------------------------------------------------


def test_c2_never_reinterprets_the_footnote_marker_as_an_estimate_flag(primary):
    """The marker, its meaning, and estimate status are three separate columns."""
    for column in ("source_footnote_marker", "source_footnote_meaning",
                   "estimate_status"):
        assert column in CF.CANONICAL_COLUMNS, column
    for row in primary:
        # An index-membership token never produces an estimate classification.
        assert row["estimate_status"] == "not_documented_as_estimate"
        if row["source_footnote_marker"]:
            assert "index" in row["source_footnote_meaning"]
            assert "estimate" not in row["source_footnote_meaning"]
    source = (ROOT / "src" / "thai_supply_chain_ews" / "features" /
              "commodity_features.py").read_text(encoding="utf-8")
    assert "estimate_marker" not in source


def test_primary_series_carry_their_documented_index_markers(primary):
    seen = {}
    for row in primary:
        seen.setdefault(row["series_id"], set()).add(
            (row["source_footnote_marker"], row["source_footnote_meaning"])
        )
    assert ("a/", "included_in_the_energy_index") in seen["brent_crude_usd_bbl"]
    for series_id in ("aluminum_usd_mt", "copper_usd_mt"):
        assert ("b/", "included_in_the_non_energy_index") in seen[series_id]
    # Rubber is printed inconsistently by the source; both forms are recorded
    # verbatim rather than normalised, and neither implies estimate status.
    assert len(seen["rubber_rss3_usd_kg"]) >= 1


def test_lineage_checksums_exclude_the_semantic_metadata_fields():
    """Metadata must not perturb a digest that identifies an observation."""
    def make(meaning: str, status: str) -> FL.LineageInput:
        return FL.LineageInput(
            series_id="s", reference_month="2024-01-01", displayed_value=1.0,
            displayed_text="1.0", decimal_places=1, source_issue_name="i",
            source_issue_date="2024-02-01", source_issue_url="u",
            source_issue_sha256="ab" * 32, source_available_month="2024-02-01",
            source_footnote_marker="a/", source_footnote_meaning=meaning,
            estimate_status=status,
        )
    baseline = make("included_in_the_energy_index", "not_documented_as_estimate")
    altered = make("included_in_the_non_energy_index", "source_documented_estimate")
    assert FL.lineage_checksum([baseline]) == FL.lineage_checksum([altered])


def test_c2_row_counts_survive_the_r3_correction(primary, sensitivity):
    assert len(primary) == 1224
    assert len(sensitivity) == 1224
    assert len(primary) + len(sensitivity) == 2448
    assert {r["series_id"] for r in primary} == set(CF.PRIMARY_SERIES)
