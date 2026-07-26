"""Build the framework architecture report from current canonical metadata."""

from __future__ import annotations

from importlib.resources import files
import pandas as pd

from sg_estate import MODEL_VERSION
from sg_estate.paths import INPUT_DIR, OUTPUT_DIR, REPOSITORY_ROOT
from sg_estate.reporting.common import atomic_write_text


def build() -> str:
    master = pd.read_csv(OUTPUT_DIR / "master_output.csv")
    life_paths = pd.read_csv(OUTPUT_DIR / "life_paths.csv")
    hdb = pd.read_csv(INPUT_DIR / "hdb_resale.csv")
    private = pd.read_csv(INPUT_DIR / "ura_private.csv")
    template = (
        files("sg_estate.reporting.templates")
        .joinpath("framework_diagram.html")
        .read_text(encoding="utf-8")
    )
    nr_count = int(master["archetype"].astype(str).str.upper().eq("X").sum())
    replacements = {
        "estate_count": len(master),
        "master_columns": len(master.columns),
        "model_version": MODEL_VERSION,
        "residential_count": len(master) - nr_count,
        "nr_count": nr_count,
        "life_path_rows": len(life_paths),
        "hdb_rows": f"{len(hdb):,}",
        "private_rows": f"{len(private):,}",
    }
    html = template
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", str(value))
    if "{{" in html or "}}" in html:
        raise ValueError("framework diagram template has unresolved placeholders")
    output = REPOSITORY_ROOT / "framework_diagram.html"
    atomic_write_text(output, html)
    print(f"Written: {output} ({len(master)} estates, {len(master.columns)} columns)")
    return html


def main() -> None:
    build()


if __name__ == "__main__":
    main()
