"""Build the cost workbook (desarrollo, mantenimiento 1 año, TCO anual) into cost/. B-23.

Assumptions must be explicit and sourced; no invented figures. See docs/COST_MODEL.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "cost" / "emerson_advisor_tco.xlsx"
SHEETS = ("Supuestos", "Desarrollo", "Mantenimiento_1_anio", "TCO_anual")


def build_workbook(out: Path) -> Path:
    """Write SHEETS with openpyxl formulas referencing the Supuestos sheet."""
    raise NotImplementedError("B-23 build_tco_excel.build_workbook")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    print(build_workbook(parser.parse_args().out))


if __name__ == "__main__":
    main()
