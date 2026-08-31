"""Product-identity semantics for the EPPO archive (Task C7.5).

C7 found the archive publishing ``FO 600 2%S`` for 66 document-days where it
otherwise publishes ``FO 600 (1) 2%S``, and refused to decide whether those name
the same series. This module is that decision, and it is built so the easy wrong
answer cannot be reached by accident.

The easy wrong answer is **numeric**. The two label forms sit at the same row,
carry adjacent prices, and the series looks continuous across the boundary. None
of that is evidence about what a label *means*: a genuinely different fuel oil
grade would also produce a continuous-looking series. :func:`evaluate_equivalence`
therefore refuses to return ``equivalence_established`` unless at least one item
of **direct semantic evidence** is present, and
:func:`assert_not_numeric_only_equivalence` raises if a caller tries to build the
decision out of price similarity.

The evidence that does count here is the workbook's own bilingual layer. From
2024-07-23 the official workbook carries a Thai companion sheet whose product
rows are *formula-bound* to the English sheet — row 14 of the Thai sheet reads
``='Oil Price Structure'!C14``. Both English label forms are bound to one and the
same Thai product name, and that name carries no ordinal marker. That is a
source-controlled data dictionary inside the official document, not an inference.

What the ordinals ``(1)`` and ``(2)`` actually mean is a separate question and is
**not** answered here. No workbook in the archive explains them and no EPPO
policy document naming them was located, so
``ordinal_marker_meaning: not_established_from_inspected_sources`` — recorded as
a limit of the sources inspected, never as proof that no explanation exists.

Establishing equivalence never rewrites a label. The raw displayed string stays
in the row; the canonical identity is a transparent layer above it.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

__all__ = [
    "CANONICAL_IDENTITY_VERSION",
    "DIRECT_SEMANTIC_EVIDENCE_KINDS",
    "EQUIVALENCE_DECISIONS",
    "EVIDENCE_CLASSES",
    "EQUIVALENCE_RULE_ID",
    "NUMERIC_ONLY_EVIDENCE_KINDS",
    "RECOVERY_STATUSES",
    "STRUCTURAL_EVIDENCE_KINDS",
    "EquivalenceError",
    "EquivalenceCandidate",
    "EquivalenceDecision",
    "SemanticEvidence",
    "assert_not_numeric_only_equivalence",
    "assert_raw_label_preserved",
    "canonical_identity",
    "collapse_label",
    "classify_recovery",
    "evaluate_equivalence",
    "parse_fuel_oil_label",
    "probe_recovery_channels",
    "thai_date_to_iso",
]

EQUIVALENCE_RULE_ID = "fo_ordinal_index_dropped_v1"
CANONICAL_IDENTITY_VERSION = "c7_5_canonical_identity_v1"

EVIDENCE_CLASSES = (
    "direct_semantic",
    "strong_structural_corroboration",
    "numeric_corroboration_only",
)

#: Evidence that can, on its own, satisfy the direct-evidence requirement.
DIRECT_SEMANTIC_EVIDENCE_KINDS = (
    "workbook_note_defines_ordinal",
    "official_formula_document_names_product_without_ordinal",
    "official_classification_equates_forms",
    "source_controlled_schema_or_data_dictionary",
)

STRUCTURAL_EVIDENCE_KINDS = (
    "same_unit",
    "same_price_stage",
    "same_sulphur_grade",
    "same_product_number",
    "same_row_position_and_neighbours",
    "labels_never_co_occur",
    "forms_replace_one_another",
    "identical_downstream_tax_and_fund_treatment",
    "consistent_formula_structure",
)

#: Evidence that may be recorded but can never carry the decision.
NUMERIC_ONLY_EVIDENCE_KINDS = (
    "adjacent_values_close",
    "series_continuous_across_boundary",
    "small_price_difference",
)

EQUIVALENCE_DECISIONS = (
    "equivalence_established",
    "equivalence_rejected",
    "equivalence_unresolved",
)

RECOVERY_STATUSES = (
    "recovered_and_validated",
    "wrong_date_attachment_unresolved",
    "official_attachment_unretrievable",
    "document_identity_unresolved",
)

_FUEL_OIL = re.compile(r"^FO\s+(?P<number>600|1500)\s*(?:\((?P<ordinal>\d)\))?\s*"
                       r"(?P<sulphur>\d+(?:\.\d+)?%S)\s*$")


class EquivalenceError(ValueError):
    """A semantic equivalence was asserted on evidence that cannot carry it."""


@dataclass
class SemanticEvidence:
    """One item of evidence, classified for what it can support."""

    evidence_class: str
    kind: str
    statement: str
    source: str
    source_checksum: str = None
    observed_in_documents: int = 0
    first_effective_date: str = None
    last_effective_date: str = None
    quotation: str = None

    def __post_init__(self):
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise EquivalenceError(f"unknown evidence class {self.evidence_class!r}")
        known = (DIRECT_SEMANTIC_EVIDENCE_KINDS + STRUCTURAL_EVIDENCE_KINDS
                 + NUMERIC_ONLY_EVIDENCE_KINDS)
        if self.kind not in known:
            raise EquivalenceError(f"unknown evidence kind {self.kind!r}")
        if (self.evidence_class == "direct_semantic"
                and self.kind not in DIRECT_SEMANTIC_EVIDENCE_KINDS):
            raise EquivalenceError(
                f"{self.kind!r} is not direct semantic evidence; classifying it as "
                "direct would let corroboration stand in for a definition"
            )
        if (self.kind in NUMERIC_ONLY_EVIDENCE_KINDS
                and self.evidence_class != "numeric_corroboration_only"):
            raise EquivalenceError(
                f"{self.kind!r} is numeric corroboration and may never be promoted "
                f"to {self.evidence_class!r}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


def parse_fuel_oil_label(label: str) -> dict:
    """Split a fuel-oil label into product number, ordinal and sulphur grade.

    Returns ``None`` for a string that is not a fuel-oil label at all, so a
    caller cannot accidentally compare a diesel row with a fuel-oil row.
    """
    found = _FUEL_OIL.match(str(label or "").strip())
    if not found:
        return None
    return {
        "raw_label": str(label),
        "product_number": found.group("number"),
        "ordinal": found.group("ordinal"),
        "sulphur_grade": found.group("sulphur"),
    }


@dataclass
class EquivalenceCandidate:
    """Everything the gate is allowed to look at for one label pair."""

    canonical_product_id: str
    label_a: str
    label_b: str
    unit_a: str
    unit_b: str
    price_stage_a: str
    price_stage_b: str
    documents_a: int = 0
    documents_b: int = 0
    co_occurring_documents: int = 0
    forms_replace_one_another: bool = False
    row_position_consistent: bool = False
    neighbours_consistent: bool = False
    downstream_treatment_identical: bool = False
    contradictory_evidence: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["evidence"] = [e.to_dict() for e in self.evidence]
        return payload


@dataclass
class EquivalenceDecision:
    decision: str
    canonical_product_id: str
    label_a: str
    label_b: str
    rule_id: str = EQUIVALENCE_RULE_ID
    canonical_identity_version: str = CANONICAL_IDENTITY_VERSION
    gate: dict = field(default_factory=dict)
    failed_conditions: list = field(default_factory=list)
    direct_evidence_count: int = 0
    structural_evidence_count: int = 0
    numeric_evidence_count: int = 0
    numeric_evidence_load_bearing: bool = False
    ordinal_marker_meaning: str = "not_established_from_inspected_sources"
    note: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def assert_not_numeric_only_equivalence(evidence) -> None:
    """Raise when the only support for a merge is that the numbers look close."""
    items = list(evidence)
    if not items:
        raise EquivalenceError(
            "no evidence supplied; equivalence may not be assumed from the "
            "absence of a contradiction"
        )
    if all(e.evidence_class == "numeric_corroboration_only" for e in items):
        raise EquivalenceError(
            "the only evidence offered is numeric corroboration. Adjacent prices "
            "and a continuous-looking series are exactly what a DIFFERENT product "
            "at the same table position would also produce, so they can never "
            "establish that two labels name the same series"
        )


def evaluate_equivalence(candidate: EquivalenceCandidate) -> EquivalenceDecision:
    """Run the eight-condition gate over one label pair.

    Every condition is reported, not just the failing one, so a near-miss is
    visible rather than reduced to a verdict.
    """
    parsed_a = parse_fuel_oil_label(candidate.label_a)
    parsed_b = parse_fuel_oil_label(candidate.label_b)
    direct = [e for e in candidate.evidence if e.evidence_class == "direct_semantic"]
    structural = [e for e in candidate.evidence
                  if e.evidence_class == "strong_structural_corroboration"]
    numeric = [e for e in candidate.evidence
               if e.evidence_class == "numeric_corroboration_only"]

    gate = {
        "direct_semantic_evidence_present": bool(direct),
        "unit_unchanged": (
            candidate.unit_a == candidate.unit_b == "BAHT/LITRE"
        ),
        "price_stage_unchanged": (
            candidate.price_stage_a == candidate.price_stage_b == "EX-REFIN."
        ),
        "product_number_unchanged": bool(
            parsed_a and parsed_b
            and parsed_a["product_number"] == parsed_b["product_number"]
        ),
        "sulphur_grade_unchanged": bool(
            parsed_a and parsed_b
            and parsed_a["sulphur_grade"] == parsed_b["sulphur_grade"]
        ),
        "no_contradictory_evidence": not candidate.contradictory_evidence,
        "labels_never_co_occur": candidate.co_occurring_documents == 0,
        "structural_corroboration_consistent": bool(
            structural
            and candidate.forms_replace_one_another
            and candidate.row_position_consistent
            and candidate.neighbours_consistent
            and candidate.downstream_treatment_identical
        ),
    }
    failed = sorted(name for name, passed in gate.items() if not passed)

    if not failed:
        decision = "equivalence_established"
        note = (
            "All eight gate conditions hold and at least one item of direct "
            "semantic evidence is present. Numeric corroboration was recorded but "
            "is not load-bearing."
        )
    elif (
        gate["no_contradictory_evidence"] is False
        or not gate["product_number_unchanged"]
        or not gate["sulphur_grade_unchanged"]
    ):
        # A different grade or number, an unparseable label, or a source that
        # disagrees are all statements that the two labels are NOT one product.
        decision = "equivalence_rejected"
        note = (
            "The labels describe different products, one of them is not a "
            "fuel-oil label at all, or the sources disagree."
        )
    else:
        decision = "equivalence_unresolved"
        note = (
            "The gate is not satisfied. The affected months stay blocked; the gate "
            "is not lowered to obtain a complete series."
        )

    return EquivalenceDecision(
        decision=decision,
        canonical_product_id=candidate.canonical_product_id,
        label_a=candidate.label_a,
        label_b=candidate.label_b,
        gate=gate,
        failed_conditions=failed,
        direct_evidence_count=len(direct),
        structural_evidence_count=len(structural),
        numeric_evidence_count=len(numeric),
        numeric_evidence_load_bearing=False,
        note=note,
    )


def collapse_label(label: str) -> str:
    """Collapse runs of whitespace in a displayed label, without changing it.

    The workbook writes ``FO 600  2%S`` with the double space left behind by the
    deleted ordinal, and C7 stored the whitespace-collapsed form. Matching on the
    collapsed form lets both spellings resolve to one identity while the exact
    displayed string is still what gets carried through and reported.
    """
    return re.sub(r"\s+", " ", str(label or "")).strip()


def canonical_identity(raw_label: str, decisions) -> dict:
    """Map a raw displayed label to its canonical identity, without rewriting it.

    ``source_product_label_raw`` is always the string that was passed in. Only
    ``canonical_product_id`` is derived, and only where a decision granted it.
    """
    raw = str(raw_label)
    collapsed = collapse_label(raw)
    for decision in decisions:
        if decision.decision != "equivalence_established":
            continue
        forms = (collapse_label(decision.label_a), collapse_label(decision.label_b))
        if collapsed in forms:
            variant = (
                "source_label_variant_equivalence_established"
                if collapsed == forms[1] else "exact_audited_label"
            )
            return {
                "source_product_label_raw": raw,
                "canonical_product_id": decision.canonical_product_id,
                "semantic_equivalence_rule_id": decision.rule_id,
                "canonical_identity_version": decision.canonical_identity_version,
                "label_variant_status": variant,
            }
    return {
        "source_product_label_raw": raw,
        "canonical_product_id": None,
        "semantic_equivalence_rule_id": None,
        "canonical_identity_version": CANONICAL_IDENTITY_VERSION,
        "label_variant_status": "equivalence_not_established",
    }


def assert_raw_label_preserved(row: dict, expected_raw: str) -> None:
    """Raise if a canonical mapping has overwritten the displayed source label."""
    actual = row.get("source_product_label_raw", row.get("source_product_label"))
    if str(actual) != str(expected_raw):
        raise EquivalenceError(
            f"raw source label {expected_raw!r} was replaced by {actual!r}; the "
            "canonical identity is a layer above the raw table, never a rewrite"
        )


@dataclass
class RecoveryAttempt:
    """One bounded recovery attempt against a single unresolved document-day."""

    listing_date: str
    media_id: int
    channels_inspected: list = field(default_factory=list)
    termination_condition: str = None
    status: str = "document_identity_unresolved"
    recovered_effective_date: str = None
    recovered_sha256: str = None
    recovered_source_url: str = None
    corroborating_sources: list = field(default_factory=list)
    reason: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def classify_recovery(
    listing_date: str,
    media_id: int,
    channels_inspected,
    attachment_retrievable: bool,
    internal_date: str = None,
    parent_post_date: str = None,
    parent_post_title_date: str = None,
    sha256: str = None,
    source_url: str = None,
) -> RecoveryAttempt:
    """Decide what one recovery attempt established.

    A wrong-date attachment is only re-dated when **official sources independent
    of the filename** agree with the document's own internal date — here the
    parent post's publication date and the date written in its title. Agreement
    between three independent official facts is a recovery; the filename alone
    would be a silent reassignment, which is what the C7 finding refused.
    """
    attempt = RecoveryAttempt(
        listing_date=str(listing_date),
        media_id=int(media_id),
        channels_inspected=sorted(channels_inspected),
    )
    if not attachment_retrievable:
        attempt.status = "official_attachment_unretrievable"
        attempt.termination_condition = "all_official_channels_exhausted"
        attempt.reason = "official_document_not_recovered_from_inspected_channels"
        return attempt

    corroborating = []
    if parent_post_date and internal_date and str(parent_post_date)[:10] == internal_date:
        corroborating.append("parent_post_publication_date")
    if (parent_post_title_date and internal_date
            and str(parent_post_title_date)[:10] == internal_date):
        corroborating.append("parent_post_title_date")

    if internal_date and internal_date != str(listing_date):
        if len(corroborating) >= 2:
            attempt.status = "recovered_and_validated"
            attempt.recovered_effective_date = internal_date
            attempt.recovered_sha256 = sha256
            attempt.recovered_source_url = source_url
            attempt.corroborating_sources = corroborating + ["document_internal_date"]
            attempt.termination_condition = "official_corroboration_reached"
            attempt.reason = (
                "The filename date disagrees with the document, and two official "
                "sources independent of the filename agree with the document."
            )
        else:
            attempt.status = "wrong_date_attachment_unresolved"
            attempt.termination_condition = "all_official_channels_exhausted"
            attempt.reason = (
                "The attachment's internal date differs from its listing date and "
                "no independent official source resolves which is correct; it is "
                "not reassigned."
            )
        return attempt

    attempt.status = "recovered_and_validated"
    attempt.recovered_effective_date = internal_date or str(listing_date)
    attempt.recovered_sha256 = sha256
    attempt.recovered_source_url = source_url
    attempt.termination_condition = "attachment_matched_its_listing"
    return attempt


#: Thai month names as they appear in EPPO post titles, with the common
#: abbreviations. Titles are written in the Buddhist Era, so 2565 is 2022.
_THAI_MONTHS = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
    "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
    "พฤศจิกายน": 11, "ธันวาคม": 12,
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
}

_THAI_DATE = re.compile(r"(\d{1,2})\s+([฀-๿.]+)\s+(\d{4})")


def thai_date_to_iso(text: str):
    """Read a Buddhist-Era Thai date out of an official post title.

    EPPO titles its price-structure posts with the reference date in Thai, e.g.
    ``โครงสร้างราคาขายปลีกน้ำมัน 6 ธันวาคม 2565``. That date is written by the
    publisher and is independent of the attachment filename, which is exactly why
    it can corroborate a document's internal date.
    """
    found = _THAI_DATE.search(str(text or ""))
    if not found:
        return None
    day, month_name, year = found.groups()
    month = _THAI_MONTHS.get(month_name.strip())
    if month is None:
        return None
    gregorian = int(year) - 543
    if not (1900 < gregorian < 2200):
        return None
    return f"{gregorian:04d}-{month:02d}-{int(day):02d}"


#: Bounded: each target is probed through this fixed channel list once.
RECOVERY_CHANNELS = (
    "wordpress_media_record",
    "guid_and_source_url",
    "alternate_attachment_link_in_official_metadata",
    "parent_post",
    "parent_post_attached_media",
    "exact_date_rest_search",
    "attachment_page",
)

_REST = "https://www.eppo.go.th/wp-json/wp/v2"


def probe_recovery_channels(media_id: int, listing_date: str, fetch_fn,
                            accepted_magic=("xls_ole2", "xlsx_zip"),
                            detect_magic_fn=None) -> dict:
    """Walk the permitted official channels for one unresolved document-day.

    Every channel is visited at most once and the walk stops at the fixed list;
    no filename is guessed and no channel outside :data:`RECOVERY_CHANNELS` is
    consulted. The return value records what each channel said, including the
    ones that said nothing.
    """
    result = {
        "media_id": int(media_id),
        "listing_date": str(listing_date),
        "channels_inspected": [],
        "channel_results": {},
        "attachment_retrievable": False,
        "attachment_sha256": None,
        "attachment_source_url": None,
        "parent_post_id": None,
        "parent_post_date": None,
        "parent_post_title": None,
        "parent_post_title_date": None,
        "alternate_links": [],
        "termination_condition": "channel_list_exhausted",
    }

    def record(channel, payload):
        result["channels_inspected"].append(channel)
        result["channel_results"][channel] = payload

    fields = "id,date,guid,link,post,source_url,slug,media_details,mime_type"
    body, status, _ = fetch_fn(f"{_REST}/media/{media_id}?_fields={fields}")
    media = json.loads(body.decode("utf-8")) if body and status == 200 else {}
    record("wordpress_media_record", {"http_status": status, "found": bool(media)})
    source_url = media.get("source_url")
    guid = (media.get("guid") or {}).get("rendered")
    result["attachment_source_url"] = source_url
    if guid and guid != source_url:
        result["alternate_links"].append(guid)

    for channel, url in (("guid_and_source_url", source_url),
                         ("alternate_attachment_link_in_official_metadata", guid)):
        if not url:
            record(channel, {"url": None, "http_status": None})
            continue
        payload, http_status, _ = fetch_fn(url)
        magic = detect_magic_fn(payload) if (payload and detect_magic_fn) else None
        usable = bool(payload) and magic in accepted_magic
        record(channel, {"url": url, "http_status": http_status,
                         "bytes": len(payload) if payload else 0, "magic": magic})
        if usable and not result["attachment_retrievable"]:
            import hashlib

            result["attachment_retrievable"] = True
            result["attachment_sha256"] = hashlib.sha256(payload).hexdigest()
            result["attachment_source_url"] = url

    parent = media.get("post")
    result["parent_post_id"] = parent
    if parent:
        body, status, _ = fetch_fn(
            f"{_REST}/posts/{parent}?_fields=id,date,title,link"
        )
        post = json.loads(body.decode("utf-8")) if body and status == 200 else {}
        title = re.sub("<[^>]+>", "", (post.get("title") or {}).get("rendered", ""))
        result["parent_post_date"] = post.get("date")
        result["parent_post_title"] = title
        result["parent_post_title_date"] = thai_date_to_iso(title)
        record("parent_post", {"http_status": status, "title": title,
                               "date": post.get("date")})

        body, status, _ = fetch_fn(
            f"{_REST}/media?parent={parent}&per_page=50&_fields=id,slug,source_url"
        )
        siblings = json.loads(body.decode("utf-8")) if body and status == 200 else []
        record("parent_post_attached_media",
               {"http_status": status, "count": len(siblings),
                "slugs": [s.get("slug") for s in siblings]})
    else:
        record("parent_post", {"http_status": None, "found": False})
        record("parent_post_attached_media", {"http_status": None, "count": 0})

    slug = media.get("slug") or ""
    body, status, _ = fetch_fn(
        f"{_REST}/media?search={slug}&per_page=20&_fields=id,slug,source_url"
    )
    matches = json.loads(body.decode("utf-8")) if body and status == 200 else []
    record("exact_date_rest_search",
           {"http_status": status, "count": len(matches),
            "ids": [m.get("id") for m in matches]})

    page = media.get("link")
    if page:
        _, status, _ = fetch_fn(page)
        record("attachment_page", {"url": page, "http_status": status})
    else:
        record("attachment_page", {"url": None, "http_status": None})

    if result["attachment_retrievable"] and result["parent_post_title_date"]:
        result["termination_condition"] = "official_corroboration_reached"
    return result
