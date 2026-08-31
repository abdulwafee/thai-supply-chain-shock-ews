"""Commodity-proxy fitness gate — Task C3-R1.

C3 marked all 48 pairs "resolved, medium confidence" and stopped there. That
conflated two different questions:

**Is the coefficient available?**
    A mathematical question about the I/O table. C3 answered it correctly.

**Does the I/O category actually represent the named commodity for THIS
industry?**
    A semantic question about what the aggregate contains. C3 never asked it.

A coefficient can be perfectly computed and still be a poor proxy. The clearest
case in this project: IND-12's exposure to "Non-ferrous metal" is 95.7% driven by
the Jewellery sector, whose official definition reads *"jewellery using precious
metals… silver, gold and other precious metal plating"*. The number is a correct
reading of the official table and a bad proxy for the LME aluminum or copper
price. Treating `medium` crosswalk confidence as feature eligibility would have
carried that straight into a model.

The gate is evidence-driven and preregistered: it reads the industry's dominant
purchasing component sector from the official table, checks that sector's
official DEFINITION for terms indicating a different commodity dominates the
aggregate, and records the evidence string behind every verdict. No target is
consulted — none exists in C3.
"""

from __future__ import annotations

__all__ = [
    "ProxyFitnessError",
    "PROXY_FIT_STATUSES",
    "QUANTITATIVE_STATUSES",
    "decompose_direct_purchases",
    "classify_proxy_fitness",
    "apply_proxy_gate",
]

PROXY_FIT_STATUSES: tuple[str, ...] = (
    "fit_for_structural_use",
    "broad_proxy_use_with_caution",
    "not_fit_for_commodity_specific_use",
    "unresolved",
)

QUANTITATIVE_STATUSES: tuple[str, ...] = ("resolved", "unresolved")

# A proxy verdict alone does not make a pair usable. Eligibility additionally
# needs a usable DIRECTION: a null sign cannot generate a signed feature.
FEATURE_ELIGIBLE_FIT = ("fit_for_structural_use", "broad_proxy_use_with_caution")


class ProxyFitnessError(ValueError):
    """The proxy gate could not be applied as specified."""


def decompose_direct_purchases(
    table, commodity_io_code: str, industry_io_codes: tuple[str, ...]
) -> dict:
    """Which of the industry's own sectors buys the commodity aggregate, and how much.

    Official-table evidence only. This is what makes the verdict checkable rather
    than asserted.
    """
    parts = [
        (code, table.z(commodity_io_code, code))
        for code in industry_io_codes
        if table.z(commodity_io_code, code) > 0
    ]
    total = sum(value for _, value in parts)
    if not parts:
        return {
            "dominant_component": None,
            "dominant_share": None,
            "contributing_components": 0,
            "direct_purchases_observed": False,
        }
    parts.sort(key=lambda item: (-item[1], item[0]))
    return {
        "dominant_component": parts[0][0],
        "dominant_share": parts[0][1] / total,
        "contributing_components": len(parts),
        "direct_purchases_observed": True,
    }


def classify_proxy_fitness(
    commodity_id: str,
    commodity_io_code: str,
    industry_id: str,
    decomposition: dict,
    sector_definitions: dict,
    rules: dict,
) -> tuple[str, str, str]:
    """Return (status, scope, evidence) for one pair.

    Order of tests matters: a documented displacement (the aggregate is dominated
    by a different commodity for this use) overrides a high-fit designation, so a
    pair can never be promoted past contrary official evidence.
    """
    rule = rules.get(commodity_id)
    if rule is None:
        return (
            "unresolved",
            "no_preregistered_rule",
            f"No proxy rule is preregistered for {commodity_id}.",
        )

    dominant = decomposition.get("dominant_component")
    share = decomposition.get("dominant_share")

    # --- 1. displacement: is the aggregate dominated by ANOTHER commodity? ---
    terms = [term.lower() for term in rule.get("displacement_terms", [])]
    threshold = float(rule.get("displacement_dominance_threshold", 0.5))
    if dominant and terms and share is not None and share >= threshold:
        definition = sector_definitions[dominant]["definition"].lower()
        matched = sorted({term for term in terms if term in definition})
        if matched:
            return (
                "not_fit_for_commodity_specific_use",
                rule.get("displaced_scope", "aggregate_dominated_by_other_commodity"),
                (
                    f"{share:.1%} of {industry_id}'s purchases from I/O sector "
                    f"{commodity_io_code} are made by sector {dominant} "
                    f"({sector_definitions[dominant]['label']}), whose official "
                    f"definition names {matched}. Within this broad aggregate the "
                    f"input for this industry is therefore dominated by a "
                    f"different commodity than {commodity_id}."
                ),
            )

    # --- 2. explicit high-fit designation, with official justification -------
    high_fit = rule.get("high_fit_components", {})
    if dominant in high_fit and share is not None and share >= threshold:
        return (
            "fit_for_structural_use",
            rule.get("fit_scope", "commodity_specific"),
            (
                f"{share:.1%} of {industry_id}'s purchases from sector "
                f"{commodity_io_code} are made by sector {dominant} "
                f"({sector_definitions[dominant]['label']}). {high_fit[dominant]}"
            ),
        )

    # --- 3. no direct purchases: the exposure is entirely indirect -----------
    if not decomposition.get("direct_purchases_observed"):
        return (
            rule.get("no_direct_purchase_status", "broad_proxy_use_with_caution"),
            rule.get("broad_scope", "broad_aggregate"),
            (
                f"{industry_id} makes NO direct purchases from sector "
                f"{commodity_io_code}; its exposure is entirely indirect. The "
                f"aggregate remains broader than {commodity_id}, so the series is "
                "usable only as a broad proxy."
            ),
        )

    # --- 4. default: a broader aggregate with no contrary evidence -----------
    return (
        "broad_proxy_use_with_caution",
        rule.get("broad_scope", "broad_aggregate"),
        (
            f"I/O sector {commodity_io_code} is a broader official aggregate than "
            f"{commodity_id}. {industry_id}'s largest purchasing component is "
            f"{dominant} ({sector_definitions[dominant]['label']}, "
            f"{share:.1%}), and no official definition indicates a different "
            "commodity dominates. Usable as a broad proxy only."
        ),
    )


def apply_proxy_gate(
    rows: list[dict],
    table,
    crosswalks,
    sector_definitions: dict,
    config: dict,
) -> list[dict]:
    """Add the C3-R1 fitness fields to the canonical rows, in place.

    NUMERIC EXPOSURES ARE NEVER TOUCHED. An ineligible pair keeps its
    coefficient: eligibility is a usage decision, and deleting or zeroing the
    number would destroy evidence and make "not suitable" indistinguishable from
    "no exposure".
    """
    rules = config["commodity_proxy_fitness"]["rules"]
    by_industry = {crosswalk.industry_id: crosswalk for crosswalk in crosswalks}

    for row in rows:
        crosswalk = by_industry[row["industry_id"]]
        commodity_code = row["commodity_io_sector_code"]

        quantitative = (
            "resolved" if row["direct_exposure"] is not None else "unresolved"
        )
        decomposition = decompose_direct_purchases(
            table, commodity_code, crosswalk.io_sector_codes
        )

        if quantitative == "unresolved":
            status, scope, evidence = (
                "unresolved",
                "coefficient_unresolved",
                "The coefficient itself is unresolved, so proxy fitness cannot be "
                "assessed.",
            )
        else:
            status, scope, evidence = classify_proxy_fitness(
                row["commodity_series_id"], commodity_code, row["industry_id"],
                decomposition, sector_definitions, rules,
            )

        # A shared sector means two series read the SAME coefficient. That is a
        # double-counting hazard for any aggregate shock index built later.
        shared = bool(row.get("shared_io_source_sector"))
        double_counting = (
            "shared_io_sector_must_not_be_summed_or_averaged" if shared else "none"
        )

        eligible = (
            quantitative == "resolved"
            and status in FEATURE_ELIGIBLE_FIT
            and row["direction_channel"] == "cost_pressure"
        )
        if eligible:
            reason = (
                f"Coefficient resolved; proxy fitness {status}; direction "
                "cost_pressure with a usable sign."
            )
        elif quantitative == "unresolved":
            reason = "Coefficient unresolved; no default feature."
        elif status not in FEATURE_ELIGIBLE_FIT:
            reason = (
                f"Proxy fitness {status}: the coefficient is preserved, but the "
                "aggregate does not represent this commodity for this industry."
            )
        else:
            reason = (
                f"Direction channel is {row['direction_channel']} with a null "
                "sign, so no signed default feature can be generated. The "
                "coefficient is preserved."
            )

        row["quantitative_coefficient_status"] = quantitative
        row["commodity_proxy_fit_status"] = status
        row["commodity_proxy_scope"] = scope
        row["commodity_proxy_evidence"] = evidence
        row["dominant_purchasing_component"] = decomposition["dominant_component"]
        row["dominant_purchasing_component_share"] = decomposition["dominant_share"]
        row["industry_pair_feature_eligible"] = eligible
        row["feature_eligibility_reason"] = reason
        row["double_counting_risk"] = double_counting

    _validate_gate(rows)
    return rows


def _validate_gate(rows: list[dict]) -> None:
    """Fail loudly on any violation of the gate's own contract."""
    if len(rows) != 48:
        raise ProxyFitnessError(f"Expected 48 gated rows; got {len(rows)}.")

    for row in rows:
        if row["commodity_proxy_fit_status"] not in PROXY_FIT_STATUSES:
            raise ProxyFitnessError(
                f"Unknown proxy status {row['commodity_proxy_fit_status']!r}."
            )
        if row["quantitative_coefficient_status"] not in QUANTITATIVE_STATUSES:
            raise ProxyFitnessError("Unknown quantitative status.")

        # An ineligible pair must KEEP its number.
        if (
            row["quantitative_coefficient_status"] == "resolved"
            and row["direct_exposure"] is None
        ):
            raise ProxyFitnessError(
                f"{row['industry_id']}/{row['commodity_series_id']}: resolved "
                "coefficient was dropped."
            )
        if not row["industry_pair_feature_eligible"] and row[
            "quantitative_coefficient_status"
        ] == "resolved" and row["direct_exposure"] is None:
            raise ProxyFitnessError(
                "An ineligible pair had its coefficient removed. Eligibility is a "
                "usage decision, never a reason to delete evidence."
            )
        # Eligibility may never be granted past contrary evidence.
        if row["industry_pair_feature_eligible"] and row[
            "commodity_proxy_fit_status"
        ] not in FEATURE_ELIGIBLE_FIT:
            raise ProxyFitnessError(
                f"{row['industry_id']}/{row['commodity_series_id']} is eligible "
                f"despite proxy status {row['commodity_proxy_fit_status']!r}."
            )
        if row["industry_pair_feature_eligible"] and row[
            "price_increase_to_stress_sign"
        ] is None:
            raise ProxyFitnessError(
                f"{row['industry_id']}/{row['commodity_series_id']} is eligible "
                "with a null sign; no signed feature could be generated from it."
            )
        if row.get("shared_io_source_sector") and row["double_counting_risk"] == "none":
            raise ProxyFitnessError(
                f"{row['industry_id']}/{row['commodity_series_id']} shares an I/O "
                "sector but carries no double-counting risk flag."
            )
