"""Run Task B1 ingestion: current-edition OIE -> division-month table -> panel.

Thin runner. All logic lives in the installable package
(`thai_supply_chain_ews.data.{oie,ingest,build_panel,taxonomy}`); this script
only wires it together and prints a human-readable summary. It imports the
package, never the other way round, and never imports the one-off audit scripts.

Usage:
    python scripts/run_b1_ingestion.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.data.build_panel import (  # noqa: E402
    build_industry_panel,
    write_outputs,
)
from thai_supply_chain_ews.data.ingest import build_division_month_table  # noqa: E402
from thai_supply_chain_ews.data.taxonomy import load_taxonomy  # noqa: E402


def main() -> None:
    taxonomy = load_taxonomy()
    division_table = build_division_month_table()
    panel = build_industry_panel(division_table, taxonomy)
    written = write_outputs(panel)

    frame = panel.frame
    div = division_table.frame
    months = sorted({str(m) for m in frame["reference_month"]})
    eligible = int(frame["is_model_eligible"].sum())
    preliminary = int((frame["mpi_is_preliminary"] | frame["capu_is_preliminary"]).sum())

    print("=== Task B1 — current-edition OIE ingestion ===")
    print(f"taxonomy      : {taxonomy.version} ({len(taxonomy.industries)} industries)")
    for component, prov in sorted(division_table.provenance.items()):
        print(f"{component:5s} source : {prov['source_file']}")
        print(f"      sha256  : {prov['source_sha256']}")
        print(f"      edition : {prov['source_edition']} (base {prov['source_base_year']})")
        print(f"      retrieved: {prov['retrieved_at']}")
    print(f"months        : {len(months)} ({months[0]} .. {months[-1]})")
    print(f"divisions     : {sorted(div['tsic_division'].unique().tolist())}")
    print(f"division rows : {len(div)}")
    print(f"panel rows    : {len(frame)}")
    print(f"model-eligible: {eligible}")
    print(f"preliminary   : {preliminary}")
    print(f"quality flags : {sorted(frame['data_quality_flag'].unique().tolist())}")

    metadata = {
        "taxonomy_version": taxonomy.version,
        "provenance": division_table.provenance,
        "month_count": len(months),
        "first_month": months[0],
        "last_month": months[-1],
        "division_count": int(div["tsic_division"].nunique()),
        "division_row_count": int(len(div)),
        "panel_row_count": int(len(frame)),
        "model_eligible_row_count": eligible,
        "preliminary_row_count": preliminary,
        "industries": taxonomy.industry_ids,
        "excluded_divisions": {str(k): v for k, v in taxonomy.excluded_divisions.items()},
        "release_date_verified": False,
        "available_as_of_verified": False,
        "evaluation_framing": "latest_vintage_historical_data",
    }
    meta_path = PROJECT_ROOT / "docs" / "b1_ingestion_metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print("\nwritten:")
    for name, path in written.items():
        print(f"  {name}: {path.relative_to(PROJECT_ROOT)}")
    print(f"  metadata: {meta_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
