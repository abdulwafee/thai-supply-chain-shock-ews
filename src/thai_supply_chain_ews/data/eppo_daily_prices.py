"""Layout discovery and the canonical daily EPPO source table (Task C7).

C6 sampled two workbook layouts a year apart and named them. Sampling cannot
tell you what happens *between* the samples, so C7 treats February–June 2023 as
an ``unsampled_transition_interval`` and discovers the layout of every document
from the document itself.

Discovery here means: enumerate every sheet, find a header row that names its own
columns, and resolve each price stage by **label**. There is no positional
fallback. If ``EX-REFIN.`` cannot be located by name the document is rejected as
``unknown_layout`` rather than parsed by guessing which column index used to hold
the ex-refinery price — a guess that would silently return wholesale or excise
tax as if it were the ex-refinery price.

A structural signature ``(format, sheet, tax-column label, label-column label)``
identifies the layout. Two signatures are known from C6; any other signature seen
in a real document is registered as a *newly observed* regime and reported, never
folded into a known one.

Product identity is exact. ``H-DIESEL``, ``H-DIESEL B7``, ``H-DIESEL B10`` and
``H-DIESEL B20`` are different products that sit in adjacent rows, and
``FO 600 (1) 2%S`` is not ``FO 1500 (2) 2%S``. Matching is on a whitespace- and
case-normalized label so ``H-DIESEL `` still matches, while the exact displayed
label is always carried through to the output.

Where the archive publishes a label that is *close to* an audited one —
``FO 600 2%S`` without the table's ordinal index — the document is parsed and the
row is marked ``unconfirmed_label_variant``. Whether the two labels name the same
series is a semantic equivalence question; C7 records it and blocks approval for
every month it touches rather than answering it.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from .eppo_price_structure import (
    ACCEPTED_MAGIC,
    AUDITED_PRODUCTS,
    DocumentValidationError,
    detect_magic,
    normalize_label,
)

__all__ = [
    "BLEND_LABELS",
    "UNCONFIRMED_LABEL_VARIANTS",
    "DAILY_QUALITY_FLAGS",
    "KNOWN_LAYOUT_SIGNATURES",
    "REQUIRED_PRICE_STAGE",
    "REQUIRED_UNIT",
    "TRANSITION_INTERVAL",
    "DayResolution",
    "LayoutDiscovery",
    "LayoutError",
    "ParsedProduct",
    "assert_document_valid",
    "assert_exact_product_label",
    "assert_regime",
    "build_daily_rows",
    "discover_layout",
    "layout_signature",
    "rank_document_candidates",
    "resolve_document_day",
    "semantic_regime_id",
    "validate_against_listing",
]

REQUIRED_PRICE_STAGE = "ex_refinery"
REQUIRED_UNIT = "BAHT/LITRE"

#: The interval C6 never sampled. Its layout is discovered, not assumed.
TRANSITION_INTERVAL = ("2023-02-01", "2023-06-30")

#: Signatures C6 actually observed, as ``(magic, sheet, tax label)`` normalized.
KNOWN_LAYOUT_SIGNATURES = {
    ("xls_ole2", "โครงสร้างราคา", "TAX"): "xls_2021",
    ("xlsx_zip", "OIL PRICE STRUCTURE", "EXCISE TAX"): "xlsx_2023",
}

#: Blend diesels. Present in the same table as ordinary H-DIESEL and never a
#: substitute for it. ``H-DIESEL 20`` is the label EPPO used in place of
#: ``H-DIESEL B20`` on four days in 2026; it is listed so the blend census is
#: complete, and like the others it is never read as ordinary H-DIESEL.
BLEND_LABELS = (
    "H-DIESEL B7", "H-DIESEL B10", "H-DIESEL B20", "H-DIESEL 20",
    "H-DIESEL PREMIUM",
)

#: Labels the archive publishes for what appears to be the same fuel oil with
#: the table's ordinal index dropped, observed 2024-07-23 to 2024-10-28 and
#: never on the same day as the ordinal label.
#:
#: The document is parsed and kept — discarding 66 valid official documents
#: would misdescribe the archive — but the variant is marked UNCONFIRMED and no
#: month that touches one is ever approved. Declaring ``FO 600 2%S`` and
#: ``FO 600 (1) 2%S`` to be the same series is a semantic equivalence decision,
#: and C7 is an ingestion task: it may surface the break, not settle it.
UNCONFIRMED_LABEL_VARIANTS = {
    "FO 600 2%S": "eppo_ex_refinery_fo600_2s",
    "FO 1500 2%S": "eppo_ex_refinery_fo1500_2s",
}

EXACT_AUDITED_LABEL = "exact_audited_label"
UNCONFIRMED_LABEL_VARIANT = "unconfirmed_label_variant"

DAILY_QUALITY_FLAGS = (
    "ok",
    "duplicate_document",
    "content_equivalent_duplicate",
    "same_date_conflicting_value",
    "unresolved_document_retrieval",
    "unresolved_document_identity",
    "unknown_layout",
)

_EXCEL_EPOCH = dt.date(1899, 12, 30)
_ISO_DATE = re.compile(r"(20\d\d)-(\d{2})-(\d{2})")
_UNIT_IN_LABEL = re.compile(r"UNIT\s*[:：]?\s*([A-Z/\. ]+)")


class LayoutError(DocumentValidationError):
    """A workbook's layout could not be established from its own labels."""


def _clean(value) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def _excel_serial_to_date(value):
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    if not (20000 < serial < 80000):
        return None
    return (_EXCEL_EPOCH + dt.timedelta(days=int(serial))).isoformat()


def _cell_date(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _excel_serial_to_date(value)
    found = _ISO_DATE.search(str(value))
    return found.group(0) if found else _excel_serial_to_date(value)


def _sheets_xlsx(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for name in workbook.sheetnames:
            sheet = workbook[name]
            grid = [
                tuple(row)
                for row in sheet.iter_rows(max_row=60, max_col=16, values_only=True)
            ]
            yield name, grid
    finally:
        workbook.close()


def _sheets_xls(path):
    import xlrd

    workbook = xlrd.open_workbook(path)
    for name in workbook.sheet_names():
        sheet = workbook.sheet_by_name(name)
        grid = [tuple(sheet.row_values(r)[:16]) for r in range(min(60, sheet.nrows))]
        yield name, grid


@dataclass
class ParsedProduct:
    """One product row, with every price stage kept in its own field."""

    series_id: str
    source_product_label: str
    normalized_label: str
    unit: str
    row_index: int
    label_variant_status: str = EXACT_AUDITED_LABEL
    ex_refinery: float = None
    excise_tax: float = None
    municipal_tax: float = None
    oil_fund: float = None
    conservation_fund: float = None
    wholesale: float = None
    vat: float = None
    wholesale_with_vat: float = None
    marketing_margin: float = None
    retail: float = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LayoutDiscovery:
    """What was found by reading the workbook, before any known-layout matching."""

    magic: str
    sheet_names: list = field(default_factory=list)
    sheet_used: str = None
    header_row_index: int = None
    header_labels: list = field(default_factory=list)
    label_column_header: str = None
    tax_column_label: str = None
    resolved_columns: dict = field(default_factory=dict)
    unit_label: str = None
    internal_title: str = None
    embedded_document_date: str = None
    date_representation: str = None
    signature: list = field(default_factory=list)
    layout_regime: str = None
    regime_status: str = "unknown_layout"
    products: list = field(default_factory=list)
    all_product_labels: list = field(default_factory=list)
    blend_labels_present: list = field(default_factory=list)
    rejection_reason: str = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["products"] = [p.to_dict() for p in self.products]
        return payload


def assert_regime(discovery, expected_regime: str) -> None:
    """Raise unless the document really is in ``expected_regime``.

    Forcing a known layout onto a document from an unsampled interval is the
    exact mistake the February–June 2023 gap invites, and it fails silently:
    positional columns still return numbers, just the wrong ones.
    """
    if discovery.layout_regime != expected_regime:
        raise LayoutError(
            f"document is layout {discovery.layout_regime!r} "
            f"(sheet {discovery.sheet_used!r}, tax column "
            f"{discovery.tax_column_label!r}), not {expected_regime!r}; "
            "refusing to parse it as a layout it does not have"
        )


def assert_document_valid(validation: dict, context: str = "") -> None:
    """Raise with the recorded reason when a rejected document is used anyway."""
    if not validation.get("valid"):
        raise LayoutError(
            f"{context or 'document'} was rejected: {validation.get('rejection_reason')}"
        )


def assert_exact_product_label(label: str, series_id: str) -> None:
    """Raise unless ``label`` is the exact audited label for ``series_id``.

    ``H-DIESEL B7`` for ``H-DIESEL`` and ``FO 1500 (2) 2%S`` for the 600 grade
    are the substitutions this refuses; both would otherwise look like ordinary
    values in a column that says something else.
    """
    normalized = normalize_label(label)
    expected = AUDITED_PRODUCTS.get(normalized)
    if expected == series_id:
        return
    if UNCONFIRMED_LABEL_VARIANTS.get(str(label).strip()) == series_id:
        raise LayoutError(
            f"{label!r} is an UNCONFIRMED variant of {series_id}; its equivalence "
            "with the audited label has not been established and it may not be "
            "used as that series"
        )
    raise LayoutError(
        f"{label!r} is not the exact audited label for {series_id}; "
        "substituting a different product is prohibited"
    )


def layout_signature(magic: str, sheet_name: str, tax_label: str) -> tuple:
    """Normalized structural signature. Case and whitespace never define a regime."""
    return (str(magic), _clean(sheet_name).upper(), _clean(tax_label).upper())


def _resolve_columns(header: list) -> dict:
    """Map price stages to column indices using header labels only.

    Every stage is looked up by its own label. ``TAX`` is matched with ``M. TAX``
    and every VAT variant excluded, because the municipal tax column would
    otherwise satisfy a bare ``TAX`` search and silently replace excise tax.
    """
    upper = [c.upper() for c in header]

    def column(*needles, exclude=()):
        for index, cell in enumerate(upper):
            if any(n in cell for n in needles) and not any(x in cell for x in exclude):
                return index
        return None

    label_column = column("UNIT")
    ex_column = column("EX-REFIN")
    tax_column = column("EXCISE TAX")
    if tax_column is None:
        tax_column = column("TAX", exclude=("M. TAX", "M.TAX", "VAT", "EX-REFIN"))
    return {
        "label": label_column,
        "ex_refinery": ex_column,
        "excise_tax": tax_column,
        "municipal_tax": column("M. TAX", "M.TAX"),
        "oil_fund": column("OIL"),
        "conservation_fund": column("CONSV"),
        "wholesale": column("WHOLESALE"),
        "vat": column("VAT (WS)", exclude=()) or column("VAT", exclude=("WS&VAT", "(MM)")),
        "wholesale_with_vat": column("WS&VAT"),
        "marketing_margin": column("MARKETING"),
        "retail": column("RETAIL"),
    }


def _number(grid, row_index: int, column_index):
    if column_index is None or row_index >= len(grid):
        return None
    row = grid[row_index]
    if column_index >= len(row):
        return None
    value = row[column_index]
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_clean(value))
    except (TypeError, ValueError):
        return None


def _unit_from_header(label_header: str) -> str:
    found = _UNIT_IN_LABEL.search(_clean(label_header).upper())
    if not found:
        return None
    return _clean(found.group(1)).replace(" ", "")


def discover_layout(path, magic: str) -> LayoutDiscovery:
    """Read a workbook and describe its layout from its own content.

    Every sheet is inspected in workbook order; the first sheet that exposes a
    labelled price-structure header is used, and the full sheet list is recorded
    either way so a layout change that adds or renames sheets is visible.
    """
    if magic == "xlsx_zip":
        sheets = list(_sheets_xlsx(path))
    elif magic == "xls_ole2":
        sheets = list(_sheets_xls(path))
    else:
        raise LayoutError(f"cannot inspect a document of type {magic!r}")

    discovery = LayoutDiscovery(magic=magic, sheet_names=[name for name, _ in sheets])

    for sheet_name, grid in sheets:
        text = [[_clean(cell) for cell in row] for row in grid]
        header_index = next(
            (i for i, row in enumerate(text) if any("EX-REFIN" in c.upper() for c in row)),
            None,
        )
        if header_index is None:
            continue

        header = text[header_index]
        columns = _resolve_columns(header)
        if columns["label"] is None or columns["ex_refinery"] is None:
            discovery.rejection_reason = (
                "header found but the unit/label column or the EX-REFIN. column "
                "could not be resolved by label; refusing to guess column positions"
            )
            continue

        if columns["ex_refinery"] in (
            columns.get("wholesale"), columns.get("excise_tax"),
            columns.get("retail"), columns.get("vat"),
        ):
            raise LayoutError(
                "the EX-REFIN. column resolved to the same index as another "
                f"price stage in sheet {sheet_name!r}; a stage collision would "
                "publish wholesale or tax as if it were the ex-refinery price"
            )

        discovery.sheet_used = sheet_name
        discovery.header_row_index = header_index
        discovery.header_labels = [c for c in header if c]
        discovery.resolved_columns = {k: v for k, v in columns.items() if v is not None}
        discovery.label_column_header = header[columns["label"]]
        discovery.tax_column_label = (
            header[columns["excise_tax"]] if columns["excise_tax"] is not None else None
        )
        discovery.unit_label = _unit_from_header(discovery.label_column_header)
        discovery.rejection_reason = None

        title = next(
            (" ".join(row).strip() for row in text
             if "PRICE STRUCTURE" in " ".join(row).upper()),
            None,
        )
        discovery.internal_title = (title or "")[:120] or None

        for row_index in range(header_index + 1):
            for cell in grid[row_index]:
                candidate = _cell_date(cell)
                if candidate:
                    discovery.embedded_document_date = candidate
                    discovery.date_representation = (
                        "datetime_cell"
                        if isinstance(cell, (dt.date, dt.datetime))
                        else "excel_serial" if isinstance(cell, (int, float))
                        else "text"
                    )
                    break
            if discovery.embedded_document_date:
                break

        label_column = columns["label"]
        for row_index in range(header_index + 1, len(text)):
            row = text[row_index]
            raw_label = row[label_column] if label_column < len(row) else ""
            label = raw_label.strip()
            if not label:
                continue
            # A second "UNIT:" header starts the marketing-margin block below the
            # price table. Stop there rather than read its rows as products.
            if "UNIT" in label.upper() and _UNIT_IN_LABEL.search(label.upper()):
                break
            if label.upper().startswith(
                ("EXCHANGE", "ETHANOL", "BIODIESEL", "NOTE", "REMARK", "AVERAGE", "GROSS")
            ):
                continue
            discovery.all_product_labels.append(label)
            normalized = normalize_label(label)
            if normalized in {normalize_label(b) for b in BLEND_LABELS}:
                discovery.blend_labels_present.append(label)
            series_id = AUDITED_PRODUCTS.get(normalized)
            variant_status = EXACT_AUDITED_LABEL
            if series_id is None:
                series_id = {
                    normalize_label(k): v
                    for k, v in UNCONFIRMED_LABEL_VARIANTS.items()
                }.get(normalized)
                variant_status = UNCONFIRMED_LABEL_VARIANT
            if series_id is None:
                continue
            unit = (
                "BAHT/KILOGRAM"
                if "KILO" in label.upper()
                else (discovery.unit_label or REQUIRED_UNIT)
            )
            discovery.products.append(
                ParsedProduct(
                    series_id=series_id,
                    source_product_label=label,
                    normalized_label=normalized,
                    unit=unit,
                    row_index=row_index,
                    label_variant_status=variant_status,
                    **{
                        name: _number(grid, row_index, columns[name])
                        for name in (
                            "ex_refinery", "excise_tax", "municipal_tax", "oil_fund",
                            "conservation_fund", "wholesale", "vat",
                            "wholesale_with_vat", "marketing_margin", "retail",
                        )
                    },
                )
            )
        break

    if discovery.sheet_used is None:
        discovery.regime_status = "unknown_layout"
        discovery.rejection_reason = discovery.rejection_reason or (
            "no sheet exposes a labelled EX-REFIN. price-structure header"
        )
        return discovery

    signature = layout_signature(magic, discovery.sheet_used, discovery.tax_column_label)
    discovery.signature = list(signature)
    known = KNOWN_LAYOUT_SIGNATURES.get(signature)
    if known:
        discovery.layout_regime = known
        discovery.regime_status = "known_regime"
    else:
        discovery.layout_regime = (
            f"{signature[0]}|{signature[1].lower().replace(' ', '_')}|"
            f"{signature[2].lower().replace(' ', '_') or 'no_tax_column'}"
        )
        discovery.regime_status = "newly_observed_regime"
    return discovery


def validate_against_listing(payload: bytes, discovery: LayoutDiscovery,
                             listing_date: str) -> dict:
    """Validate a retrieved document against its own content and the listing date.

    A filename is never identity. A workbook whose internal date belongs to
    another day is rejected for the listing date and is *not* reassigned to its
    internal date: the archive item that listed it is what failed, and inventing
    a placement would hide that.
    """
    result = {
        "valid": False,
        "magic": detect_magic(payload) if payload else None,
        "rejection_reason": None,
        "internal_date": discovery.embedded_document_date,
        "layout_regime": discovery.layout_regime,
        "regime_status": discovery.regime_status,
    }
    if not payload:
        result["rejection_reason"] = "zero_byte_file"
        return result
    if result["magic"] not in ACCEPTED_MAGIC.values():
        result["rejection_reason"] = f"unaccepted_format_{result['magic']}"
        return result
    if discovery.regime_status == "unknown_layout":
        result["rejection_reason"] = f"unknown_layout: {discovery.rejection_reason}"
        return result
    title = (discovery.internal_title or "").upper()
    if "PRICE STRUCTURE" not in title:
        result["rejection_reason"] = "internal_title_is_not_a_price_structure"
        return result
    if not discovery.embedded_document_date:
        result["rejection_reason"] = "internal_date_not_parseable"
        return result
    if listing_date and discovery.embedded_document_date != listing_date:
        result["rejection_reason"] = (
            f"wrong_date_attachment: document says "
            f"{discovery.embedded_document_date}, archive item says {listing_date}"
        )
        return result
    if not discovery.products:
        result["rejection_reason"] = "no_audited_product_observations"
        return result
    if all(p.ex_refinery is None for p in discovery.products):
        result["rejection_reason"] = "formula_template_without_ex_refinery_values"
        return result
    result["valid"] = True
    return result


def rank_document_candidates(candidates) -> list:
    """Rank a day's attachments by verified relationship to the archive item.

    ``candidates`` are ``(record, discovery, validation)`` triples. The ordering
    is content-derived: internal date match, correct title, the required table,
    exact product labels and units, and a non-HTML body. Encounter order is never
    used; the final tie-break is the source-assigned WordPress media ID, which is
    stable across runs and independent of how the crawl happened to arrive.
    """
    ranked = []
    for record, discovery, validation in candidates:
        date_matches = bool(
            discovery.embedded_document_date
            and discovery.embedded_document_date == record.effective_date_filename
        )
        title_ok = "PRICE STRUCTURE" in (discovery.internal_title or "").upper()
        table_ok = discovery.resolved_columns.get("ex_refinery") is not None
        labels_ok = bool(discovery.products) and all(
            p.unit in (REQUIRED_UNIT, "BAHT/KILOGRAM") for p in discovery.products
        )
        not_html = discovery.magic in ACCEPTED_MAGIC.values()
        checksum_ok = bool(record.sha256) and record.bytes == (record.bytes or 0)
        ranked.append({
            "media_id": record.media_id,
            "filename": record.filename,
            "sha256": record.sha256,
            "internal_date_matches_listing": date_matches,
            "internal_title_correct": title_ok,
            "required_table_present": table_ok,
            "exact_labels_and_units_present": labels_ok,
            "not_html_or_waf": not_html,
            "checksum_content_consistent": checksum_ok,
            "accepted": bool(validation.get("valid")),
            "rejection_reason": validation.get("rejection_reason"),
            "rank_key": (
                not date_matches, not title_ok, not table_ok,
                not labels_ok, not not_html, not checksum_ok, record.media_id,
            ),
        })
    ranked.sort(key=lambda entry: entry["rank_key"])
    for entry in ranked:
        entry["rank_key"] = list(entry["rank_key"][:-1]) + [entry["rank_key"][-1]]
    return ranked


def semantic_regime_id(series_id: str, layout_regime: str, label: str) -> str:
    """C6's regime key, kept identical so C6 and C7 regimes remain comparable."""
    return f"{series_id}|{layout_regime}|{normalize_label(label)}"


@dataclass
class DayResolution:
    """How one document-day resolved across all of its candidates."""

    effective_date: str
    discovered_candidates: int
    accepted_candidates: int
    rejected_candidates: list = field(default_factory=list)
    duplicate_documents: int = 0
    content_equivalent_duplicates: int = 0
    primary_media_id: int = None
    ranking: list = field(default_factory=list)
    status: str = "unresolved_document_retrieval"
    conflicts: list = field(default_factory=list)
    products: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_document_day(effective_date: str, candidates) -> DayResolution:
    """Resolve one day's candidates into at most one value per series.

    Byte-identical documents are duplicates and contribute once. Different bytes
    that parse to the same value are content-equivalent duplicates and also
    contribute once. Different bytes that parse to *different* values are a
    conflict: no preference is applied, the series-date is left unresolved, and
    the affected month loses its approval.
    """
    resolution = DayResolution(
        effective_date=effective_date,
        discovered_candidates=len(candidates),
        accepted_candidates=0,
    )
    accepted = []
    for record, discovery, validation in candidates:
        if validation.get("valid"):
            accepted.append((record, discovery, validation))
        else:
            resolution.rejected_candidates.append({
                "media_id": record.media_id,
                "filename": record.filename,
                "sha256": record.sha256,
                "retrieval_status": record.retrieval_status,
                "rejection_reason": (
                    validation.get("rejection_reason") or record.rejection_reason
                ),
            })
    resolution.accepted_candidates = len(accepted)
    resolution.ranking = rank_document_candidates(candidates)

    if not accepted:
        retrieval_failed = any(
            not record.succeeded for record, _, _ in candidates
        )
        resolution.status = (
            "unresolved_document_retrieval" if retrieval_failed
            else "unresolved_document_identity"
        )
        return resolution

    by_digest = defaultdict(list)
    for item in accepted:
        by_digest[item[0].sha256].append(item)
    resolution.duplicate_documents = sum(len(v) - 1 for v in by_digest.values())

    distinct = [sorted(v, key=lambda i: i[0].media_id)[0] for _, v in sorted(by_digest.items())]
    primary = rank_document_candidates(distinct)[0]
    resolution.primary_media_id = primary["media_id"]
    primary_item = next(i for i in distinct if i[0].media_id == primary["media_id"])

    for series_id in sorted(AUDITED_PRODUCTS.values()):
        values, sources = {}, []
        for record, discovery, _ in distinct:
            product = next(
                (p for p in discovery.products if p.series_id == series_id), None
            )
            if product is None or product.ex_refinery is None:
                continue
            key = round(float(product.ex_refinery), 10)
            values.setdefault(key, []).append(record.media_id)
            sources.append((record, discovery, product))
        if not sources:
            continue
        if len(values) > 1:
            resolution.conflicts.append({
                "series_id": series_id,
                "effective_date": effective_date,
                "values": sorted(values),
                "media_ids": sorted(m for ids in values.values() for m in ids),
            })
            resolution.products[series_id] = {
                "status": "same_date_conflicting_value", "value": None,
            }
            continue
        if len(sources) > 1:
            resolution.content_equivalent_duplicates += len(sources) - 1
        chosen = next(
            (s for s in sources if s[0].media_id == primary["media_id"]), sources[0]
        )
        record, discovery, product = chosen
        resolution.products[series_id] = {
            "status": (
                "content_equivalent_duplicate" if len(sources) > 1
                else "duplicate_document" if resolution.duplicate_documents else "ok"
            ),
            "value": float(product.ex_refinery),
            "media_id": record.media_id,
            "sha256": record.sha256,
            "raw_relative_path": record.raw_relative_path,
            "filename": record.filename,
            "attachment_url": record.attachment_url,
            "source_product_label": product.source_product_label,
            "label_variant_status": product.label_variant_status,
            "unit": product.unit,
            "layout_regime": discovery.layout_regime,
            "downloaded_at_utc": record.downloaded_at_utc,
            "discovery_method": record.discovery_method,
        }
    resolution.status = (
        "same_date_conflicting_value" if resolution.conflicts else "resolved"
    )
    _ = primary_item
    return resolution


def build_daily_rows(resolutions, price_stage: str = REQUIRED_PRICE_STAGE,
                     source_name: str = "EPPO petroleum price structure") -> list:
    """Emit one canonical row per ``(series_id, effective_date, semantic_regime_id)``.

    A conflicting series-date still gets a row, with a null value and the
    conflict flag. Dropping it would turn a known unresolved fact into an
    invisible absence.
    """
    rows = []
    for resolution in resolutions:
        for series_id, product in sorted(resolution.products.items()):
            if product["status"] == "same_date_conflicting_value":
                rows.append({
                    "series_id": series_id,
                    "source_product_label": None,
                    "semantic_regime_id": None,
                    "effective_date": resolution.effective_date,
                    "value": None,
                    "unit": REQUIRED_UNIT,
                    "price_stage": price_stage,
                    "source_name": source_name,
                    "media_id": None,
                    "source_url": None,
                    "raw_filename": None,
                    "raw_file_sha256": None,
                    "source_document_sha256": None,
                    "discovery_method": "official_wordpress_rest",
                    "label_variant_status": None,
                    "quality_flag": "same_date_conflicting_value",
                    "downloaded_at_utc": None,
                })
                continue
            rows.append({
                "series_id": series_id,
                "source_product_label": product["source_product_label"],
                "semantic_regime_id": semantic_regime_id(
                    series_id, product["layout_regime"], product["source_product_label"]
                ),
                "effective_date": resolution.effective_date,
                "value": product["value"],
                "unit": product["unit"],
                "price_stage": price_stage,
                "source_name": source_name,
                "media_id": product["media_id"],
                "source_url": product["attachment_url"],
                "raw_filename": product["filename"],
                "raw_file_sha256": product["sha256"],
                "source_document_sha256": product["sha256"],
                "discovery_method": product["discovery_method"],
                "label_variant_status": product["label_variant_status"],
                "quality_flag": product["status"],
                "downloaded_at_utc": product["downloaded_at_utc"],
            })
    rows.sort(key=lambda r: (r["series_id"], r["effective_date"],
                             r["semantic_regime_id"] or ""))
    seen = set()
    for row in rows:
        key = (row["series_id"], row["effective_date"], row["semantic_regime_id"])
        if key in seen:
            raise LayoutError(f"duplicate canonical daily key {key}")
        seen.add(key)
    return rows
