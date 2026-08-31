"""World Bank Pink Sheet parser and source-eligibility audit (Task C1).

Production implementation. Scripts call this module; they do not re-implement
parsing.

SCOPE — this module deliberately produces LEVELS ONLY. It does not compute
month-over-month change, year-over-year change, lags, volatility, z-scores, or
shock flags; it does not convert units; and it never touches the forecast
target. Those are feature-engineering decisions that need their own timing and
semantics gate (Task C2).

Workbook layout (verified against the real August 2026 vintage, not assumed):

    row 0-3  title and "Updated on <date>" lines
    row 4    series labels          e.g. "Crude oil, Brent"
    row 5    units in parentheses   e.g. "($/bbl)"
    row 6+   observations, column 0 holding "1960M01"-style period codes
    missing  the single-character ellipsis "…"

Some labels carry a trailing "**" marking a Description-sheet footnote; the
marker is part of the printed label and is stripped for matching but preserved
in `source_series_label` so the audit trail stays faithful to the file.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover
    raise ImportError("openpyxl is required to parse the Pink Sheet workbook") from exc

__all__ = [
    "CANONICAL_COLUMNS",
    "CandidateAudit",
    "PinkSheetLayoutError",
    "PinkSheetWorkbook",
    "SeriesNotFoundError",
    "DuplicateLabelError",
    "audit_candidates",
    "build_canonical_table",
    "classify_cross_check",
    "compute_cross_check_metrics",
    "parse_fred_monthly_csv",
    "default_config_path",
    "load_commodity_config",
    "parse_period_code",
    "parse_workbook",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PERIOD_PATTERN = re.compile(r"^\s*(\d{4})M(\d{1,2})\s*$")
MISSING_TOKENS = {"…", "...", "", "-", "n/a", "na"}
FOOTNOTE_MARKER = "*"

CANONICAL_COLUMNS = [
    "series_id",
    "source_series_label",
    "month",
    "value",
    "unit",
    "currency",
    "frequency",
    "source_name",
    "source_url",
    "source_vintage",
    "downloaded_at_utc",
    "raw_file_sha256",
    "source_verified",
    "quality_flag",
    "release_date",
    "available_as_of",
    "point_in_time_supported",
]


class PinkSheetLayoutError(ValueError):
    """The workbook does not match the verified Pink Sheet layout."""


class SeriesNotFoundError(KeyError):
    """A configured source label is absent from the workbook.

    Raised rather than falling back to a fuzzy match — silently substituting a
    different commodity is precisely the failure this project forbids.
    """


class DuplicateLabelError(ValueError):
    """One label appears in more than one column; the intended series is ambiguous."""


def default_config_path() -> Path:
    return PROJECT_ROOT / "configs" / "upstream_commodity_sources.yaml"


def load_commodity_config(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else default_config_path()
    if not path.is_file():
        raise FileNotFoundError(f"Commodity source config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_period_code(value) -> date:
    """"1960M01" -> date(1960, 1, 1). Rejects anything else explicitly.

    Also accepts a real datetime/date, because a future workbook vintage could
    store the period column as an Excel date rather than a string; an Excel
    serial number is NOT silently accepted, since guessing its epoch is how
    dates end up shifted by years.
    """
    if isinstance(value, (pd.Timestamp,)):
        return date(value.year, value.month, 1)
    if hasattr(value, "year") and hasattr(value, "month") and not isinstance(value, str):
        return date(value.year, value.month, 1)
    if not isinstance(value, str):
        raise PinkSheetLayoutError(
            f"Unparseable period value {value!r} ({type(value).__name__}); refusing to guess."
        )
    match = PERIOD_PATTERN.match(value)
    if not match:
        raise PinkSheetLayoutError(f"Period code {value!r} does not match YYYYMmm.")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise PinkSheetLayoutError(f"Period code {value!r} has an invalid month.")
    return date(year, month, 1)


def _clean_label(label: str) -> str:
    return label.replace(FOOTNOTE_MARKER, "").strip()


def _parse_unit(raw_unit) -> tuple[str, str | None]:
    """"($/bbl)" -> ("$/bbl", "USD"). Returns (unit, currency)."""
    if raw_unit is None:
        return "", None
    text = str(raw_unit).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    currency = "USD" if text.startswith("$") else None
    return text, currency


def _parse_value(cell) -> tuple[float | None, str]:
    """Return (value, quality_flag). Missing tokens are NOT imputed."""
    if cell is None:
        return None, "missing"
    if isinstance(cell, str):
        if cell.strip().lower() in MISSING_TOKENS or cell.strip() == "…":
            return None, "missing"
        try:
            parsed = float(cell.replace(",", "").strip())
        except ValueError:
            return None, "non_numeric"
        return parsed, "ok"
    if isinstance(cell, bool):
        return None, "non_numeric"
    if isinstance(cell, (int, float)):
        if not math.isfinite(float(cell)):
            return None, "non_finite"
        return float(cell), "ok"
    return None, "non_numeric"


@dataclass
class PinkSheetWorkbook:
    file_path: Path
    sheet_names: list[str]
    labels_by_column: dict[int, str]
    units_by_column: dict[int, str]
    months: list[date]
    values: dict[int, list]  # column index -> raw cell values aligned to `months`
    updated_on: str | None
    description_entries: list[str] = field(default_factory=list)

    def column_for_label(self, label: str) -> int:
        wanted = _clean_label(label).lower()
        matches = [
            col for col, name in self.labels_by_column.items()
            if _clean_label(name).lower() == wanted
        ]
        if not matches:
            raise SeriesNotFoundError(
                f"Series label {label!r} not found in the workbook. Available labels are "
                "recorded in the audit output; no fuzzy substitution is performed."
            )
        if len(matches) > 1:
            raise DuplicateLabelError(
                f"Series label {label!r} appears in {len(matches)} columns {matches}; "
                "the intended series is ambiguous."
            )
        return matches[0]


def parse_workbook(path: Path, config: dict | None = None) -> PinkSheetWorkbook:
    config = config or load_commodity_config()
    layout = config["primary_source"]["header_layout"]
    data_sheet = config["primary_source"]["data_sheet"]
    description_sheet = config["primary_source"]["description_sheet"]

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet_names = list(workbook.sheetnames)
        if data_sheet not in sheet_names:
            raise PinkSheetLayoutError(
                f"Expected sheet {data_sheet!r}; workbook has {sheet_names}. "
                "The workbook layout changed — refusing to guess which sheet holds prices."
            )
        rows = list(workbook[data_sheet].iter_rows(values_only=True))

        label_row = rows[int(layout["label_row"])]
        unit_row = rows[int(layout["unit_row"])]
        first_data_row = int(layout["first_data_row"])
        date_column = int(layout["date_column"])

        labels_by_column = {
            col: str(name).strip()
            for col, name in enumerate(label_row)
            if name is not None and str(name).strip()
        }
        if not labels_by_column:
            raise PinkSheetLayoutError(
                f"No series labels found on row {layout['label_row']} — layout changed."
            )
        units_by_column = {
            col: str(unit_row[col]).strip()
            for col in labels_by_column
            if col < len(unit_row) and unit_row[col] is not None
        }

        months: list[date] = []
        values: dict[int, list] = {col: [] for col in labels_by_column}
        for row in rows[first_data_row:]:
            period = row[date_column] if date_column < len(row) else None
            if period is None or (isinstance(period, str) and not period.strip()):
                continue  # trailing blank row, not an observation
            try:
                month = parse_period_code(period)
            except PinkSheetLayoutError:
                # A footnote line below the data block is not an observation.
                continue
            months.append(month)
            for col in labels_by_column:
                values[col].append(row[col] if col < len(row) else None)

        if not months:
            raise PinkSheetLayoutError("Parsed zero observation rows — layout changed.")

        updated_on = None
        for row in rows[: first_data_row]:
            for cell in row:
                if isinstance(cell, str) and cell.strip().lower().startswith("updated on"):
                    updated_on = cell.strip()
        description_entries: list[str] = []
        if description_sheet in sheet_names:
            for row in workbook[description_sheet].iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    joined = " ".join(cells).strip()
                    if len(joined) > 30:
                        description_entries.append(joined)
        return PinkSheetWorkbook(
            file_path=path,
            sheet_names=sheet_names,
            labels_by_column=labels_by_column,
            units_by_column=units_by_column,
            months=months,
            values=values,
            updated_on=updated_on,
            description_entries=description_entries,
        )
    finally:
        workbook.close()


# --- audit -------------------------------------------------------------------


@dataclass
class CandidateAudit:
    candidate_id: str
    intended_source_series: str
    resolved_source_label: str
    found: bool
    unit: str
    currency: str | None
    expected_unit: str
    unit_matches_expected: bool
    first_observation: str | None
    last_observation: str | None
    total_observations: int
    required_window_rows: int
    required_window_expected: int
    missing_in_required_window: int
    missingness_pct: float
    duplicate_months: int
    minimum: float | None
    maximum: float | None
    median: float | None
    non_positive_count: int
    largest_one_month_pct_move: float | None
    largest_move_month: str | None
    definition_notes: list[str] = field(default_factory=list)
    definition_break_months: list[str] = field(default_factory=list)
    definition_break_in_window: bool = False
    criteria: dict = field(default_factory=dict)
    status: str = "rejected"
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    source_verified: bool = False
    feature_semantics_approved: bool = False
    model_feature_approved: bool = False


_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
# Any "MonthName YYYY" in a definition note marks a regime boundary. An earlier
# version anchored on "from|beginning|during|since", which silently MISSED
# boundaries written as bare ranges — e.g. palm oil's "November 2024-January
# 2025" and "January 2021 to October 2024" regimes. Under-reporting a
# definition break is the dangerous direction, so every dated mention is
# extracted and adjudicated against the window; the verbatim note is kept
# alongside so a human can confirm.
_DATED_CHANGE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{4})\b")
_BARE_YEAR = re.compile(r"\b(19|20)(\d{2})\b")


def _month_range(start: date, end: date) -> list[date]:
    out, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(date(year, month, 1))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return out


def _find_definition_notes(workbook: PinkSheetWorkbook, label: str) -> list[str]:
    """Description entries that plausibly describe this series.

    Matched on the leading commodity word(s) because the Description sheet uses
    a different naming style than the price header (e.g. "Coal (Australia)" vs
    "Coal, Australian").
    """
    head = _clean_label(label).split(",")[0].strip().lower()
    qualifier = ""
    if "," in _clean_label(label):
        qualifier = _clean_label(label).split(",", 1)[1].strip().lower()
        qualifier = re.sub(r"[^a-z]", "", qualifier)[:5]
    notes = []
    for entry in workbook.description_entries:
        low = entry.lower()
        if not low.lstrip("* ").startswith(head):
            continue
        if qualifier and qualifier not in re.sub(r"[^a-z]", "", low):
            continue
        notes.append(entry)
    return notes


def _definition_break_months(notes: list[str]) -> list[str]:
    """Every dated regime boundary mentioned in a definition note."""
    months: list[str] = []
    for note in notes:
        for month_name, year in _DATED_CHANGE.findall(note):
            number = _MONTH_NAMES.get(month_name.lower())
            if number:
                months.append(f"{int(year):04d}-{number:02d}-01")
    return sorted(set(months))


def _definition_break_years(notes: list[str]) -> list[int]:
    """Year-only boundaries, e.g. "settlement price beginning 2005"."""
    years: set[int] = set()
    for note in notes:
        for century, rest in _BARE_YEAR.findall(note):
            years.add(int(f"{century}{rest}"))
    return sorted(years)


def audit_candidates(
    workbook: PinkSheetWorkbook, config: dict, provenance: dict
) -> list[CandidateAudit]:
    """Apply the preregistered eligibility gate to every configured candidate."""
    criteria = config["eligibility_criteria"]
    window_start = criteria["required_window"]["start"]
    window_end = criteria["required_window"]["end"]
    if isinstance(window_start, str):
        window_start = date.fromisoformat(window_start)
    if isinstance(window_end, str):
        window_end = date.fromisoformat(window_end)
    definition_window = criteria["definition_break_window"]
    def_start, def_end = definition_window["start"], definition_window["end"]
    if isinstance(def_start, str):
        def_start = date.fromisoformat(def_start)
    if isinstance(def_end, str):
        def_end = date.fromisoformat(def_end)
    max_missing = float(criteria["max_missingness_pct_in_required_window"])

    required_months = _month_range(window_start, window_end)
    results: list[CandidateAudit] = []

    for spec in config["candidates"]:
        label = spec["resolved_source_label"]
        expected_unit = str(spec["expected_unit"])
        reasons: list[str] = []
        flags: list[str] = []

        try:
            column = workbook.column_for_label(label)
            found = True
        except (SeriesNotFoundError, DuplicateLabelError) as exc:
            results.append(
                CandidateAudit(
                    candidate_id=spec["candidate_id"],
                    intended_source_series=spec["intended_source_series"],
                    resolved_source_label=label,
                    found=False, unit="", currency=None, expected_unit=expected_unit,
                    unit_matches_expected=False, first_observation=None,
                    last_observation=None, total_observations=0,
                    required_window_rows=0, required_window_expected=len(required_months),
                    missing_in_required_window=len(required_months), missingness_pct=100.0,
                    duplicate_months=0, minimum=None, maximum=None, median=None,
                    non_positive_count=0, largest_one_month_pct_move=None,
                    largest_move_month=None,
                    status="rejected", reasons=[str(exc)],
                )
            )
            continue

        raw_unit = workbook.units_by_column.get(column)
        unit, currency = _parse_unit(raw_unit)
        unit_matches = _parse_unit(expected_unit)[0] == unit
        if not unit_matches:
            reasons.append(f"unit {unit!r} does not match expected {expected_unit!r}")

        parsed = [_parse_value(cell) for cell in workbook.values[column]]
        series = {
            workbook.months[i]: value
            for i, (value, flag) in enumerate(parsed)
            if flag == "ok" and value is not None
        }
        non_numeric = sum(1 for _, flag in parsed if flag == "non_numeric")
        non_finite = sum(1 for _, flag in parsed if flag == "non_finite")
        if non_numeric:
            flags.append(f"{non_numeric}_non_numeric_cells")
        if non_finite:
            reasons.append(f"{non_finite} non-finite values present")

        duplicate_months = len(workbook.months) - len(set(workbook.months))
        if duplicate_months:
            reasons.append(f"{duplicate_months} duplicate month(s) in the workbook")

        present_required = [m for m in required_months if m in series]
        missing_required = len(required_months) - len(present_required)
        missingness_pct = 100.0 * missing_required / len(required_months)
        if missingness_pct > max_missing:
            reasons.append(
                f"missingness {missingness_pct:.2f}% in the required window exceeds "
                f"{max_missing}%"
            )

        ordered_months = sorted(series)
        values_sorted = [series[m] for m in ordered_months]
        non_positive = sum(1 for v in values_sorted if v <= 0)
        if non_positive:
            flags.append(f"{non_positive}_non_positive_values")

        largest_move, largest_month = None, None
        for previous, current in zip(ordered_months, ordered_months[1:], strict=False):
            if (current.year * 12 + current.month) - (
                previous.year * 12 + previous.month
            ) != 1:
                continue
            base = series[previous]
            if base <= 0:
                continue
            move = abs(series[current] / base - 1.0) * 100.0
            if largest_move is None or move > largest_move:
                largest_move, largest_month = move, current.isoformat()
        if largest_move is not None and largest_move >= 50.0:
            # Flagged, never removed: commodity prices really do move this much.
            flags.append("large_one_month_move_flagged_not_removed")

        notes = _find_definition_notes(workbook, label)
        break_months = _definition_break_months(notes)
        in_window = [m for m in break_months if def_start.isoformat() <= m <= def_end.isoformat()]
        for year in _definition_break_years(notes):
            if def_start.year <= year <= def_end.year:
                marker = f"{year:04d}-year-only"
                if not any(m.startswith(f"{year:04d}") for m in in_window):
                    in_window.append(marker)
        in_window = sorted(in_window)
        if in_window:
            reasons.append(
                f"definition/benchmark change dated inside {def_start:%Y-%m}..{def_end:%Y-%m}: "
                f"{in_window}"
            )
        if any("estimate" in note.lower() for note in notes):
            flags.append("source_states_recent_months_are_estimates")

        gate = {
            "found_in_official_workbook": found,
            "exact_label_and_unit_documented": bool(unit) and unit_matches,
            "dates_parse_to_unambiguous_gregorian_months": True,
            "no_duplicate_month": duplicate_months == 0,
            "covers_required_window": missing_required == 0 or missingness_pct <= max_missing,
            "missingness_within_limit": missingness_pct <= max_missing,
            "all_values_finite": non_finite == 0,
            "no_unexplained_unit_change": unit_matches,
            "no_unresolved_definition_break_in_window": not in_window,
            "provenance_recorded": all(
                provenance.get(k) for k in ("source_url", "downloaded_at_utc", "sha256")
            ),
            "deterministically_reproducible": True,
        }
        if not gate["provenance_recorded"]:
            reasons.append("provenance (url/timestamp/checksum) incomplete")

        # STATUS TIERING, applied mechanically:
        #   source_verified — every preregistered criterion holds
        #   conditional     — the DATA is sound (found, complete, finite, no
        #                     duplicate months) but a documented SEMANTIC issue
        #                     is unresolved: a unit mismatch, or a definition /
        #                     benchmark break dated inside the window
        #   rejected        — the data itself is unusable or absent
        # The distinction matters: a conditional series can be rehabilitated by
        # resolving the semantics, a rejected one cannot.
        data_is_sound = (
            gate["found_in_official_workbook"]
            and gate["missingness_within_limit"]
            and gate["all_values_finite"]
            and gate["no_duplicate_month"]
            and gate["provenance_recorded"]
        )
        if all(gate.values()):
            status = "source_verified"
        elif data_is_sound:
            status = "conditional"
        else:
            status = "rejected"

        results.append(
            CandidateAudit(
                candidate_id=spec["candidate_id"],
                intended_source_series=spec["intended_source_series"],
                resolved_source_label=label,
                found=found,
                unit=unit,
                currency=currency,
                expected_unit=expected_unit,
                unit_matches_expected=unit_matches,
                first_observation=ordered_months[0].isoformat() if ordered_months else None,
                last_observation=ordered_months[-1].isoformat() if ordered_months else None,
                total_observations=len(ordered_months),
                required_window_rows=len(present_required),
                required_window_expected=len(required_months),
                missing_in_required_window=missing_required,
                missingness_pct=missingness_pct,
                duplicate_months=duplicate_months,
                minimum=min(values_sorted) if values_sorted else None,
                maximum=max(values_sorted) if values_sorted else None,
                median=float(pd.Series(values_sorted).median()) if values_sorted else None,
                non_positive_count=non_positive,
                largest_one_month_pct_move=largest_move,
                largest_move_month=largest_month,
                definition_notes=notes,
                definition_break_months=break_months,
                definition_break_in_window=bool(in_window),
                criteria=gate,
                status=status,
                reasons=reasons or ["All preregistered eligibility criteria met."],
                flags=flags,
                source_verified=status == "source_verified",
                feature_semantics_approved=False,  # not evaluated in C1
                model_feature_approved=False,  # must remain false in C1
            )
        )
    return results


# --- canonical table ---------------------------------------------------------


def build_canonical_table(
    workbook: PinkSheetWorkbook,
    audits: list[CandidateAudit],
    config: dict,
    provenance: dict,
) -> pd.DataFrame:
    """One row per (series_id, month), levels only.

    The full valid source history is preserved — not just the required window —
    because truncating history at ingestion would silently constrain what later
    tasks can do. Missing months are simply absent: no forward-fill, no
    interpolation.
    """
    primary = config["primary_source"]
    records: list[dict] = []
    for audit in audits:
        if not audit.found:
            continue
        column = workbook.column_for_label(audit.resolved_source_label)
        for i, month in enumerate(workbook.months):
            value, flag = _parse_value(workbook.values[column][i])
            if value is None:
                continue  # never imputed
            records.append(
                {
                    "series_id": audit.candidate_id,
                    "source_series_label": audit.resolved_source_label,
                    "month": month,
                    "value": value,
                    "unit": audit.unit,
                    "currency": audit.currency,
                    "frequency": "monthly",
                    "source_name": primary["source_name"],
                    "source_url": provenance["source_url"],
                    "source_vintage": provenance.get("source_vintage"),
                    "downloaded_at_utc": provenance["downloaded_at_utc"],
                    "raw_file_sha256": provenance["sha256"],
                    "source_verified": audit.source_verified,
                    "quality_flag": flag,
                    # Historical release vintages are not available for this
                    # source. Emitting the download date here would assert that
                    # every past month was available on that date, which is
                    # false and would silently license a point-in-time claim.
                    "release_date": None,
                    "available_as_of": None,
                    "point_in_time_supported": False,
                }
            )

    frame = pd.DataFrame.from_records(records, columns=CANONICAL_COLUMNS)
    frame = frame.sort_values(["series_id", "month"], kind="mergesort").reset_index(drop=True)
    duplicated = frame.duplicated(subset=["series_id", "month"])
    if duplicated.any():
        raise ValueError(
            f"Duplicate (series_id, month) keys:\n{frame.loc[duplicated, ['series_id','month']]}"
        )
    frame["month"] = pd.to_datetime(frame["month"]).dt.date
    frame["value"] = frame["value"].astype("float64")
    frame["source_verified"] = frame["source_verified"].astype("bool")
    frame["point_in_time_supported"] = frame["point_in_time_supported"].astype("bool")
    for column in ("series_id", "source_series_label", "unit", "currency", "frequency",
                   "source_name", "source_url", "source_vintage", "downloaded_at_utc",
                   "raw_file_sha256", "quality_flag"):
        frame[column] = frame[column].astype("string")
    for column in ("release_date", "available_as_of"):
        frame[column] = pd.Series([pd.NaT] * len(frame), dtype="datetime64[ns]")
    return frame


# --- Brent cross-check -------------------------------------------------------


def parse_fred_monthly_csv(path: Path, series_id: str) -> dict[date, float]:
    """Parse a FRED `fredgraph.csv` export into {month: value}.

    FRED marks missing observations with "."; those months are omitted, never
    imputed. The observation date is FRED's period start, which for a monthly
    series is already the first of the month — no realignment is applied,
    because silently shifting one series' dates is exactly how a spurious
    cross-check agreement (or disagreement) gets manufactured.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    frame = pd.read_csv(path)
    date_column = frame.columns[0]
    if series_id not in frame.columns:
        raise SeriesNotFoundError(
            f"FRED CSV has no column {series_id!r}; found {list(frame.columns)}"
        )
    out: dict[date, float] = {}
    for raw_date, raw_value in zip(frame[date_column], frame[series_id], strict=True):
        text = str(raw_value).strip()
        if text in {".", "", "nan", "NaN"}:
            continue
        stamp = pd.to_datetime(raw_date)
        out[date(stamp.year, stamp.month, 1)] = float(text)
    return out


def compute_cross_check_metrics(
    world_bank: dict[date, float], fred: dict[date, float], start: date, end: date
) -> dict:
    """Descriptive comparison of two Brent series over an overlap window."""
    window = _month_range(start, end)
    common = [m for m in window if m in world_bank and m in fred]
    missing_wb = [m.isoformat() for m in window if m not in world_bank]
    missing_fred = [m.isoformat() for m in window if m not in fred]
    if not common:
        return {
            "common_month_count": 0,
            "missing_in_world_bank": missing_wb,
            "missing_in_fred": missing_fred,
            "pearson": None, "spearman": None, "mean_abs_diff": None,
            "median_abs_pct_diff": None, "max_abs_diff": None,
            "largest_discrepancy_months": [],
        }
    a = pd.Series([world_bank[m] for m in common], dtype=float)
    b = pd.Series([fred[m] for m in common], dtype=float)
    diff = (a - b).abs()
    pct = (diff / b.abs().replace(0, pd.NA) * 100.0).astype(float)
    ordered = sorted(
        zip([m.isoformat() for m in common], diff.tolist(), strict=True),
        key=lambda kv: kv[1], reverse=True,
    )
    return {
        "common_month_count": len(common),
        "missing_in_world_bank": missing_wb,
        "missing_in_fred": missing_fred,
        "pearson": float(a.corr(b, method="pearson")),
        # Spearman = Pearson on average ranks. Computed directly rather than via
        # pandas' method="spearman", which delegates to scipy — not a dependency
        # of this project, and not worth adding for one correlation.
        "spearman": float(
            a.rank(method="average").corr(b.rank(method="average"), method="pearson")
        ),
        "mean_abs_diff": float(diff.mean()),
        "median_abs_pct_diff": float(pct.median()),
        "max_abs_diff": float(diff.max()),
        "largest_discrepancy_months": [
            {"month": m, "abs_diff": d} for m, d in ordered[:5]
        ],
    }


def classify_cross_check(metrics: dict, config: dict) -> tuple[str, list[str]]:
    """Apply the preregistered Consistent / Inconsistent / Conditional rule."""
    rules = config["cross_check_classification"]
    consistent = rules["consistent"]
    inconsistent = rules["inconsistent"]
    reasons: list[str] = []

    if metrics.get("pearson") is None or metrics["common_month_count"] == 0:
        return rules["not_executed_state"], [
            "No overlapping observations were available to compare."
        ]

    pearson = metrics["pearson"]
    median_pct = metrics["median_abs_pct_diff"]
    months = metrics["common_month_count"]

    if pearson < float(inconsistent["max_pearson_exclusive"]) or median_pct > float(
        inconsistent["min_median_abs_pct_diff_exclusive"]
    ):
        reasons.append(
            f"Pearson {pearson:.4f} or median abs pct diff {median_pct:.2f}% breaches the "
            "inconsistent boundary."
        )
        return "inconsistent", reasons

    if (
        months >= int(consistent["min_common_months"])
        and pearson >= float(consistent["min_pearson"])
        and median_pct <= float(consistent["max_median_abs_pct_diff"])
    ):
        return "consistent", ["All preregistered consistency thresholds met."]

    if months < int(consistent["min_common_months"]):
        reasons.append(f"Only {months} common months (< {consistent['min_common_months']}).")
    if pearson < float(consistent["min_pearson"]):
        reasons.append(f"Pearson {pearson:.4f} < {consistent['min_pearson']}.")
    if median_pct > float(consistent["max_median_abs_pct_diff"]):
        reasons.append(
            f"Median abs pct diff {median_pct:.2f}% > {consistent['max_median_abs_pct_diff']}%."
        )
    return "conditional", reasons
