"""Import-safe entry point for the estate comparison report."""

from pathlib import Path
import runpy

from sg_estate.paths import REPOSITORY_ROOT


def build() -> Path:
    """Render the comparison report from promoted pipeline outputs."""

    runpy.run_module(
        "sg_estate.reporting.builders._comparison_impl",
        run_name="__main__",
    )
    return REPOSITORY_ROOT / "comparison_table.html"


def main() -> None:
    build()


if __name__ == "__main__":
    main()
