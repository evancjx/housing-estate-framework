"""Import-safe entry point for the MRT comparison report."""

from pathlib import Path
import runpy

from sg_estate.paths import REPOSITORY_ROOT


def build() -> Path:
    """Render the MRT comparison report from promoted pipeline outputs."""

    runpy.run_module(
        "sg_estate.reporting.builders._mrt_comparison_impl",
        run_name="__main__",
    )
    return REPOSITORY_ROOT / "mrt_comparison_table.html"


def main() -> None:
    build()


if __name__ == "__main__":
    main()
