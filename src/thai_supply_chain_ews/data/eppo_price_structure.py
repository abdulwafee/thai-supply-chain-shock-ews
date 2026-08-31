"""Parsing and validation of EPPO petroleum price-structure workbooks (Task C6).

The archive spans two layout regimes and the difference is not cosmetic:

=================  ==========================  ==============================
regime             ``xls_2021`` (.xls, OLE2)   ``xlsx_2023`` (.xlsx, ZIP)
sheet              ``โครงสร้างราคา``            ``Oil Price Structure``
label column       0                            1
date cell          Excel serial, row 1          datetime, row 4
tax column header  ``TAX``                      ``EXCISE TAX``
=================  ==========================  ==============================

Product labels also move. ``H-DIESEL B7`` exists in 2021 and 2023 but is absent
by 2026; the plain ``H-DIESEL`` label appears with one, two or trailing spaces.
Matching on a normalized label and recording the **exact displayed label** keeps
those apart, and a definition change becomes an explicit semantic regime rather
than a silent splice.

Validation is against the document's own content, never its filename. An HTML
error page saved with an ``.xlsx`` name, a workbook whose internal date belongs
to another day, or a file with no observations are all rejected explicitly.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, field

__all__ = [
    "ACCEPTED_MAGIC",
    "AUDITED_PRODUCTS",
    "PRICE_STAGE_COLUMNS",
    "DocumentValidationError",
    "ParsedDocument",
    "ProductObservation",
    "detect_magic",
    "normalize_label",
    "parse_workbook",
    "validate_document",
]

ACCEPTED_MAGIC = {
    b"PK\x03\x04": "xlsx_zip",
    b"\xd0\xcf\x11\xe0": "xls_ole2",
}

#: Only the sector-093 candidates C5 justified structurally.
AUDITED_PRODUCTS = {
    "H-DIESEL": "eppo_ex_refinery_hsd",
    "FO 600 (1) 2%S": "eppo_ex_refinery_fo600_2s",
    "FO 1500 (2) 2%S": "eppo_ex_refinery_fo1500_2s",
}

#: Stage columns are kept apart on purpose: substituting wholesale or retail for
#: ex-refinery would silently change which price stage the series represents.
PRICE_STAGE_COLUMNS = (
    "ex_refinery", "excise_tax", "municipal_tax", "oil_fund",
    "conservation_fund", "wholesale", "vat", "wholesale_with_vat",
)

_EXCEL_EPOCH = dt.date(1899, 12, 30)
_ISO_DATE = re.compile(r"(20\d\d)-(\d{2})-(\d{2})")


class DocumentValidationError(ValueError):
    """A retrieved document failed validation against its own content."""


def detect_magic(payload: bytes) -> str:
    """Identify the real format from magic bytes, never from the extension."""
    for signature, name in ACCEPTED_MAGIC.items():
        if payload.startswith(signature):
            return name
    head = payload[:512].lstrip().lower()
    if head.startswith(b"<!doctype") or b"<html" in head:
        return "html_masquerade"
    return "unknown"


def normalize_label(label: str) -> str:
    """Collapse whitespace and case so ``H-DIESEL `` and ``H-DIESEL`` match.

    The EXACT displayed label is always kept alongside; this only decides
    membership, never what gets reported.
    """
    return re.sub(r"\s+", " ", str(label or "")).strip().upper()


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
    if isinstance(value, (int, float)):
        return _excel_serial_to_date(value)
    found = _ISO_DATE.search(str(value))
    if found:
        return found.group(0)
    return _excel_serial_to_date(value)


@dataclass
class ProductObservation:
    series_id: str
    source_product_label: str
    normalized_label: str
    ex_refinery: float = None
    excise_tax: float = None
    municipal_tax: float = None
    oil_fund: float = None
    conservation_fund: float = None
    wholesale: float = None
    vat: float = None
    wholesale_with_vat: float = None
    unit: str = None
    row_index: int = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedDocument:
    layout_regime: str
    sheet_name: str
    internal_title: str = None
    embedded_document_date: str = None
    unit_label: str = None
    header_labels: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    all_product_labels: list = field(default_factory=list)
    tax_column_label: str = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["observations"] = [o.to_dict() for o in self.observations]
        return payload


def _grid_from_xlsx(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        grid = [tuple(row) for row in sheet.iter_rows(max_row=40, max_col=12, values_only=True)]
        return grid, workbook.sheetnames[0]
    finally:
        workbook.close()


def _grid_from_xls(path):
    import xlrd

    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_index(0)
    grid = [tuple(sheet.row_values(r)[:12]) for r in range(min(40, sheet.nrows))]
    return grid, workbook.sheet_names()[0]


def parse_workbook(path, magic: str) -> ParsedDocument:
    """Parse one workbook into stage-separated product observations."""
    if magic == "xlsx_zip":
        grid, sheet_name = _grid_from_xlsx(path)
        regime = "xlsx_2023"
    elif magic == "xls_ole2":
        grid, sheet_name = _grid_from_xls(path)
        regime = "xls_2021"
    else:
        raise DocumentValidationError(f"cannot parse a document of type {magic!r}")

    text = [["" if c is None else str(c) for c in row] for row in grid]

    title = None
    for row in text:
        joined = " ".join(row)
        if "PRICE STRUCTURE" in joined.upper():
            title = joined.strip()
            break

    header_index = None
    for index, row in enumerate(text):
        if any("EX-REFIN" in cell.upper() for cell in row):
            header_index = index
            break
    if header_index is None:
        raise DocumentValidationError("no EX-REFIN. header found; not a price-structure sheet")

    header = text[header_index]
    label_column = next(
        (i for i, cell in enumerate(header) if "UNIT" in cell.upper()), 0
    )
    ex_column = next(i for i, cell in enumerate(header) if "EX-REFIN" in cell.upper())
    unit_label = header[label_column].strip() or None

    def column_for(*needles, exclude=()):
        for i, cell in enumerate(header):
            upper = cell.upper()
            if any(n in upper for n in needles) and not any(x in upper for x in exclude):
                return i
        return None

    tax_column = column_for("EXCISE TAX") or column_for("TAX", exclude=("M. TAX", "VAT"))
    columns = {
        "ex_refinery": ex_column,
        "excise_tax": tax_column,
        "municipal_tax": column_for("M. TAX"),
        "oil_fund": column_for("OIL"),
        "conservation_fund": column_for("CONSV"),
        "wholesale": column_for("WHOLESALE"),
        "vat": column_for("VAT", exclude=("WS&VAT",)),
        "wholesale_with_vat": column_for("WS&VAT"),
    }

    def number(row_index, column_index):
        if column_index is None or row_index >= len(grid):
            return None
        row = grid[row_index]
        if column_index >= len(row):
            return None
        value = row[column_index]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    observations, labels = [], []
    for index in range(header_index + 1, len(text)):
        raw_label = text[index][label_column] if label_column < len(text[index]) else ""
        label = raw_label.strip()
        if not label or label.upper().startswith(("EXCHANGE", "ETHANOL", "BIODIESEL", "NOTE")):
            continue
        labels.append(label)
        normalized = normalize_label(label)
        series_id = AUDITED_PRODUCTS.get(normalized)
        if series_id is None:
            continue
        observations.append(
            ProductObservation(
                series_id=series_id,
                source_product_label=label,
                normalized_label=normalized,
                unit=("BAHT/KILOGRAM" if "KILO" in label.upper() else "BAHT/LITRE"),
                row_index=index,
                **{name: number(index, column) for name, column in columns.items()},
            )
        )

    embedded = None
    for row in grid[: header_index + 1]:
        for cell in row:
            candidate = _cell_date(cell)
            if candidate:
                embedded = candidate
                break
        if embedded:
            break

    return ParsedDocument(
        layout_regime=regime,
        sheet_name=sheet_name,
        internal_title=(title or "")[:120] or None,
        embedded_document_date=embedded,
        unit_label=unit_label,
        header_labels=[c.strip() for c in header if c.strip()],
        observations=observations,
        all_product_labels=labels,
        tax_column_label=(header[tax_column].strip() if tax_column is not None else None),
    )


def validate_document(payload: bytes, path, expected_date: str, parsed=None) -> dict:
    """Validate a retrieved attachment against its own content.

    ``expected_date`` is the archive item's date. A mismatch against the
    document's internal date is a rejection, not a note: it is exactly how a
    detail page linking to the wrong dated workbook shows itself.
    """
    magic = detect_magic(payload)
    result = {
        "bytes": len(payload),
        "magic": magic,
        "accepted_format": magic in ACCEPTED_MAGIC.values(),
        "html_masquerade": magic == "html_masquerade",
        "valid": False,
        "rejection_reason": None,
    }
    if not payload:
        result["rejection_reason"] = "zero_byte_file"
        return result
    if magic == "html_masquerade":
        result["rejection_reason"] = "html_page_served_as_document"
        return result
    if not result["accepted_format"]:
        result["rejection_reason"] = f"unaccepted_format_{magic}"
        return result

    try:
        document = parsed if parsed is not None else parse_workbook(path, magic)
    except DocumentValidationError as error:
        result["rejection_reason"] = str(error)[:120]
        return result

    result["layout_regime"] = document.layout_regime
    result["internal_title"] = document.internal_title
    result["embedded_document_date"] = document.embedded_document_date

    if not document.internal_title or "PRICE STRUCTURE" not in document.internal_title.upper():
        result["rejection_reason"] = "internal_title_is_not_a_price_structure"
        return result
    if not document.embedded_document_date:
        result["rejection_reason"] = "internal_date_not_parseable"
        return result
    if expected_date and document.embedded_document_date != expected_date:
        result["rejection_reason"] = (
            f"wrong_date_attachment: document says {document.embedded_document_date}, "
            f"archive item says {expected_date}"
        )
        return result
    if not document.observations:
        result["rejection_reason"] = "no_audited_product_observations"
        return result
    if all(o.ex_refinery is None for o in document.observations):
        result["rejection_reason"] = "formula_template_without_observations"
        return result

    result["valid"] = True
    return result
