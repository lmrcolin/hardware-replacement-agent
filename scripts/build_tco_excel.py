"""Build the cost workbook (desarrollo, mantenimiento 1 año, TCO anual) into cost/ (B-23).

Every input lives in the "Supuestos" sheet as a named cell, typed DATO (sourced fact) or SUPUESTO
(editable assumption, highlighted). Other sheets only hold formulas over those names, so changing
an assumption recalculates the whole workbook. Inventory figures come from the real catalog PDF.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.worksheet import Worksheet

from advisor.config import REPO_ROOT
from advisor.ingestion import discover_documents
from advisor.models import CommercialInformation, DocumentType
from advisor.parsing import parse_catalog

DEFAULT_OUT = REPO_ROOT / "cost" / "emerson_advisor_tco.xlsx"
SHEETS = ("Supuestos", "Desarrollo", "Mantenimiento_1_anio", "TCO_anual", "Inventario")
CATALOG_PDF = "Catalogo_Comercial_Precios_Inventario_2026.pdf"

BOLD = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
ASSUMPTION_FILL = PatternFill("solid", fgColor="FFF2CC")
USD = '#,##0.00 "USD"'
PCT = "0.0%"


@dataclass(frozen=True)
class Input:
    name: str
    label: str
    value: float
    unit: str
    kind: str  # DATO | SUPUESTO
    source: str


INPUTS: tuple[Input, ...] = (
    Input(
        "personas_equipo",
        "Personas en el equipo",
        3,
        "personas",
        "DATO",
        "Equipo del datathon (3 personas)",
    ),
    Input("horas_reto", "Duración del reto", 24, "h", "DATO", "Reto de 24 h (Datathon MICAI 2026)"),
    Input(
        "objetivo_inventario_usd",
        "Inventario a mover por año (meta)",
        4_000_000,
        "USD/año",
        "DATO",
        "Meta del Reto 1 de Emerson",
    ),
    Input(
        "costo_apis_hackathon_usd",
        "Costo de APIs durante el reto",
        0,
        "USD",
        "DATO",
        "Regla del reto: APIs = 0 USD (Free Edition + plantilla/Ollama)",
    ),
    Input(
        "horas_efectivas_persona",
        "Horas productivas por persona en el reto",
        20,
        "h/persona",
        "SUPUESTO",
        "SUPUESTO EDITABLE: horas útiles de las 24 del reto",
    ),
    Input(
        "tarifa_usd_hora",
        "Tarifa de desarrollo",
        30,
        "USD/h",
        "SUPUESTO",
        "SUPUESTO EDITABLE: reemplazar por la tarifa interna de Emerson",
    ),
    Input(
        "horas_endurecimiento",
        "Horas para pasar de prototipo a piloto",
        120,
        "h",
        "SUPUESTO",
        "SUPUESTO EDITABLE: seguridad, CI/CD, monitoreo, UI final",
    ),
    Input(
        "horas_mantenimiento_mes",
        "Mantenimiento (reglas, monitoreo, soporte)",
        12,
        "h/mes",
        "SUPUESTO",
        "SUPUESTO EDITABLE",
    ),
    Input(
        "actualizaciones_catalogo_anio",
        "Actualizaciones de catálogo por año",
        12,
        "veces/año",
        "SUPUESTO",
        "SUPUESTO EDITABLE: una por mes",
    ),
    Input(
        "horas_por_actualizacion",
        "Horas por actualización de catálogo",
        2,
        "h",
        "SUPUESTO",
        "SUPUESTO EDITABLE: subir PDFs + run_all + revisar JoinReport",
    ),
    Input(
        "dbu_por_ejecucion",
        "DBU por ejecución del job run_all",
        2,
        "DBU",
        "SUPUESTO",
        "POR CONFIRMAR: medir en system.billing.usage tras un run",
    ),
    Input(
        "ejecuciones_mes",
        "Ejecuciones del pipeline por mes",
        4,
        "veces/mes",
        "SUPUESTO",
        "SUPUESTO EDITABLE",
    ),
    Input(
        "warehouse_horas_mes",
        "Horas de SQL warehouse por mes",
        40,
        "h/mes",
        "SUPUESTO",
        "SUPUESTO EDITABLE",
    ),
    Input(
        "dbu_hora_warehouse",
        "DBU por hora del warehouse 2X-Small",
        4,
        "DBU/h",
        "SUPUESTO",
        "POR CONFIRMAR en la documentación de precios de Databricks",
    ),
    Input(
        "usd_por_dbu",
        "Precio por DBU (plan de pago)",
        0.7,
        "USD/DBU",
        "SUPUESTO",
        "POR CONFIRMAR: depende de plan, nube y tipo de cómputo; Free Edition = 0",
    ),
    Input(
        "consultas_mes",
        "Consultas de clientes por mes",
        1000,
        "consultas/mes",
        "SUPUESTO",
        "SUPUESTO EDITABLE",
    ),
    Input(
        "tokens_por_consulta",
        "Tokens LLM por consulta (NLU + NLG)",
        3000,
        "tokens",
        "SUPUESTO",
        "SUPUESTO EDITABLE: medir con trazas reales",
    ),
    Input(
        "usd_por_millon_tokens",
        "Precio LLM por millón de tokens",
        1.0,
        "USD/1M tokens",
        "SUPUESTO",
        "POR CONFIRMAR: precio pay-per-token de Llama 3.3 70B en FMAPI; plantilla = 0",
    ),
    Input(
        "hosting_app_usd_mes",
        "Hospedaje de la app",
        50,
        "USD/mes",
        "SUPUESTO",
        "SUPUESTO EDITABLE: Databricks App o VM pequeña",
    ),
    Input("contingencia_pct", "Contingencia", 0.15, "%", "SUPUESTO", "SUPUESTO EDITABLE"),
)


def _header(ws: Worksheet, row: int, titles: list[str]) -> None:
    for col, title in enumerate(titles, start=1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.font, cell.fill = BOLD, HEADER_FILL


def _widths(ws: Worksheet, widths: list[int]) -> None:
    for i, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = width


def _supuestos(wb: Workbook) -> None:
    ws = wb.active
    assert ws is not None
    ws.title = "Supuestos"
    ws["A1"] = "Supuestos y datos del modelo de costos (las celdas amarillas son editables)"
    ws["A1"].font = Font(bold=True, size=12)
    _header(ws, 3, ["Parámetro", "Valor", "Unidad", "Tipo", "Fuente / nota", "Nombre"])
    for row, item in enumerate(INPUTS, start=4):
        ws.cell(row=row, column=1, value=item.label)
        value = ws.cell(row=row, column=2, value=item.value)
        ws.cell(row=row, column=3, value=item.unit)
        ws.cell(row=row, column=4, value=item.kind)
        ws.cell(row=row, column=5, value=item.source)
        ws.cell(row=row, column=6, value=item.name)
        if item.kind == "SUPUESTO":
            value.fill = ASSUMPTION_FILL
        if item.unit == "%":
            value.number_format = PCT
        wb.defined_names[item.name] = DefinedName(item.name, attr_text=f"Supuestos!$B${row}")
    _widths(ws, [44, 14, 16, 12, 70, 30])


def _table(
    ws: Worksheet, title: str, rows: list[tuple[str, str, str, str]], total_label: str
) -> int:
    """rows: (concepto, cantidad formula, unidad, costo formula). Returns the total row."""
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=12)
    _header(ws, 3, ["Concepto", "Cantidad", "Unidad", "Costo"])
    for i, (concept, qty, unit, cost) in enumerate(rows, start=4):
        ws.cell(row=i, column=1, value=concept)
        ws.cell(row=i, column=2, value=qty).number_format = "#,##0.##"
        ws.cell(row=i, column=3, value=unit)
        ws.cell(row=i, column=4, value=cost).number_format = USD
    total = 4 + len(rows)
    ws.cell(row=total, column=1, value=total_label).font = BOLD
    cell = ws.cell(row=total, column=4, value=f"=SUM(D4:D{total - 1})")
    cell.font, cell.number_format = BOLD, USD
    _widths(ws, [52, 16, 14, 18])
    return total


def _inventario(wb: Workbook, catalog: list[CommercialInformation]) -> tuple[str, str, str]:
    ws = wb.create_sheet("Inventario")
    ws["A1"] = f"Inventario según el catálogo ({CATALOG_PDF}). El precio solo existe para ACTIVE."
    ws["A1"].font = BOLD
    _header(
        ws,
        3,
        ["Part number", "Descripción", "Categoría", "Status", "Precio USD", "Stock", "Valor USD"],
    )
    first = 4
    for i, row in enumerate(catalog, start=first):
        ws.cell(row=i, column=1, value=row.part_number)
        ws.cell(row=i, column=2, value=row.description)
        ws.cell(row=i, column=3, value=row.category.value)
        ws.cell(row=i, column=4, value=row.status.value)
        ws.cell(
            row=i, column=5, value=float(row.price_usd) if row.price_usd is not None else None
        ).number_format = USD
        ws.cell(row=i, column=6, value=row.stock_units)
        ws.cell(row=i, column=7, value=f'=IF(D{i}="ACTIVE",E{i}*F{i},0)').number_format = USD
    last = first + len(catalog) - 1
    summary = last + 2
    ws.cell(row=summary, column=1, value="Valor del inventario ACTIVE").font = BOLD
    ws.cell(row=summary, column=7, value=f"=SUM(G{first}:G{last})").number_format = USD
    ws.cell(
        row=summary + 1,
        column=1,
        value="Unidades en stock de piezas no ACTIVE (sin precio vigente)",
    ).font = BOLD
    ws.cell(
        row=summary + 1, column=6, value=f'=SUMIF(D{first}:D{last},"<>ACTIVE",F{first}:F{last})'
    )
    ws.cell(
        row=summary + 2, column=1, value="Piezas no ACTIVE (DISCONTINUED, EOL, NRND)"
    ).font = BOLD
    ws.cell(row=summary + 2, column=6, value=f'=COUNTIF(D{first}:D{last},"<>ACTIVE")')
    _widths(ws, [20, 38, 16, 14, 14, 10, 18])
    return (
        f"Inventario!$G${summary}",
        f"Inventario!$F${summary + 1}",
        f"Inventario!$F${summary + 2}",
    )


def build_workbook(out: Path, catalog: list[CommercialInformation] | None = None) -> Path:
    if catalog is None:
        records = discover_documents(REPO_ROOT / "data" / "raw")
        catalog = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    wb = Workbook()
    _supuestos(wb)

    dev = wb.create_sheet("Desarrollo")
    dev_total = _table(
        dev,
        "Desarrollo (inversión única)",
        [
            (
                "Prototipo en el datathon (personas x horas efectivas)",
                "=personas_equipo*horas_efectivas_persona",
                "h",
                "=B4*tarifa_usd_hora",
            ),
            (
                "Endurecimiento de prototipo a piloto",
                "=horas_endurecimiento",
                "h",
                "=B5*tarifa_usd_hora",
            ),
            ("APIs durante el reto", "=costo_apis_hackathon_usd", "USD", "=B6"),
        ],
        "Total desarrollo",
    )

    ops = wb.create_sheet("Mantenimiento_1_anio")
    ops_total = _table(
        ops,
        "Mantenimiento y operación (12 meses)",
        [
            (
                "Mantenimiento: reglas, monitoreo, soporte",
                "=horas_mantenimiento_mes*12",
                "h",
                "=B4*tarifa_usd_hora",
            ),
            (
                "Actualización del catálogo y datasheets",
                "=actualizaciones_catalogo_anio*horas_por_actualizacion",
                "h",
                "=B5*tarifa_usd_hora",
            ),
            (
                "Databricks: ejecuciones del pipeline",
                "=dbu_por_ejecucion*ejecuciones_mes*12",
                "DBU",
                "=B6*usd_por_dbu",
            ),
            (
                "Databricks: SQL warehouse",
                "=warehouse_horas_mes*12*dbu_hora_warehouse",
                "DBU",
                "=B7*usd_por_dbu",
            ),
            (
                "LLM (NLU + NLG)",
                "=consultas_mes*12*tokens_por_consulta",
                "tokens",
                "=B8/1000000*usd_por_millon_tokens",
            ),
            ("Hospedaje de la app", "=12", "meses", "=B9*hosting_app_usd_mes"),
        ],
        "Total mantenimiento 1 año",
    )

    inventory_value, non_active_units, non_active_parts = _inventario(wb, catalog)

    tco = wb.create_sheet("TCO_anual", 3)
    tco["A1"] = "Costo total de propiedad (TCO)"
    tco["A1"].font = Font(bold=True, size=12)
    _header(tco, 3, ["Concepto", "Valor"])
    lines = [
        ("Desarrollo (año 1)", f"=Desarrollo!$D${dev_total}", USD),
        ("Mantenimiento y operación (año)", f"=Mantenimiento_1_anio!$D${ops_total}", USD),
        ("Subtotal año 1", "=B4+B5", USD),
        ("Contingencia", "=B6*contingencia_pct", USD),
        ("TCO año 1", "=B6+B7", USD),
        ("TCO años siguientes (sin desarrollo)", "=B5*(1+contingencia_pct)", USD),
        ("Meta: inventario a mover por año", "=objetivo_inventario_usd", USD),
        ("TCO año 1 / meta de inventario", "=B8/B10", PCT),
        ("Valor del inventario ACTIVE en catálogo (dato)", f"={inventory_value}", USD),
        ("Unidades en stock de piezas no ACTIVE (dato)", f"={non_active_units}", "#,##0"),
        ("Piezas no ACTIVE en catálogo (dato)", f"={non_active_parts}", "#,##0"),
    ]
    for i, (label, formula, fmt) in enumerate(lines, start=4):
        tco.cell(row=i, column=1, value=label)
        tco.cell(row=i, column=2, value=formula).number_format = fmt
    for row in (8, 9):
        tco.cell(row=row, column=1).font = BOLD
        tco.cell(row=row, column=2).font = BOLD
    tco["A17"] = (
        "Lectura: el TCO depende de supuestos editables (hoja Supuestos, celdas amarillas). "
        "Los marcados POR CONFIRMAR deben validarse con precios oficiales antes de usar "
        "estas cifras."
    )
    tco["A17"].alignment = Alignment(wrap_text=True)
    tco.merge_cells("A17:B19")
    _widths(tco, [52, 22])

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    print(build_workbook(parser.parse_args().out))


if __name__ == "__main__":
    main()
