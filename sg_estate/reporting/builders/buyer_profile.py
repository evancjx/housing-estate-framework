"""Import-safe entry point for the buyer-profile report."""

from pathlib import Path
import runpy

from sg_estate.paths import REPOSITORY_ROOT


def build() -> Path:
    """Render the buyer-profile report from committed model outputs."""

    runpy.run_module(
        "sg_estate.reporting.builders._buyer_profile_impl",
        run_name="__main__",
    )
    return REPOSITORY_ROOT / "buyer_profile_table.html"


def main() -> None:
    build()


if __name__ == "__main__":
    main()

