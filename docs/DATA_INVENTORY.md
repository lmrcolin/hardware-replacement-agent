# Inventario de datos — `data/raw/`

Inspección: 2026-11-03. Los PDFs no se modifican; viven en `data/raw/`, ruta que usa `databricks/notebooks/00_setup.py` para copiarlos al volumen.

## Resumen

- 33 PDFs: 1 catálogo comercial (2 páginas) + 32 datasheets (31 de 1 página, 1 de 2 páginas).
- El catálogo lista **32 part numbers**: ACTIVE 21, DISCONTINUED 6, EOL 2, NRND 3.
- Solo 4 datasheets declaran `Product Status:` explícito (E810, USB-2627 → DISCONTINUED; A100 → NRND; ConnectX-7 → ACTIVE). Todos coinciden con el catálogo. **El catálogo es la fuente de verdad del estado.**
- Con posibles avisos de migración/sustitución en el texto (heurística por palabras clave, sin verificar): A100, USB-2627, ConnectX-7, Cortex-A78, RTX 4090, Artix-7.

## Catálogo ↔ datasheet (mapeo propuesto, a confirmar por `enrichment.join_catalog`)

| Part number (catálogo) | Categoría | Status | Datasheet |
|---|---|---|---|
| Cortex-A78 | CPU | NRND | arm-cortex-a78-trm.pdf |
| EPYC-9654 | CPU | ACTIVE | amd-epyc-9004-datasheet.pdf (familia) |
| w9-3595X | CPU | ACTIVE | intel-xeon-w9-3595x-datasheet.pdf |
| AD7606 | DAQ | ACTIVE | AD7606-datasheet.pdf |
| USB-1608GX | DAQ | DISCONTINUED | USB-1608GX-data.pdf |
| USB-1808X | DAQ | ACTIVE | USB-1808X_High-Speed_DAQ.pdf |
| USB-2627 | DAQ | DISCONTINUED | USB-2627_Multifunction_DAQ.pdf |
| USB-2633 | DAQ | ACTIVE | USB-2633_Multifunction_DAQ.pdf |
| USB-6001 | DAQ | EOL | NI-USB-6001-datasheet.pdf |
| AGFB014R24A | FPGA | ACTIVE | intel-agilex7-datasheet.pdf (familia) |
| ICE40UP5K | FPGA | ACTIVE | lattice-ice40-datasheet.pdf (familia) |
| XC7A200T | FPGA | NRND | xilinx-artix7-datasheet.pdf (familia) |
| A100-SXM4-80GB | GPU | NRND | NVIDIA_A100_80GB_GPU.pdf |
| H100-SXM5 | GPU | ACTIVE | NVIDIA_H100_SXM5_GPU.pdf |
| MI300X | GPU | ACTIVE | amd-mi300x-datasheet.pdf |
| RTX-4090 | GPU | ACTIVE | nvidia-rtx4090-datasheet.pdf |
| H3A8G32AMR | Memory | ACTIVE | samsung-hbm3-datasheet.pdf |
| H9HCNNNCPMML | Memory | ACTIVE | sk-hynix-lpddr5x-datasheet.pdf |
| MT60B4G8HB-48B | Memory | ACTIVE | micron-ddr5-datasheet.pdf |
| ATSAMD21G18A | Microcontroller | DISCONTINUED | atsamd21-datasheet.pdf (familia) |
| ESP32-S3 | Microcontroller | ACTIVE | esp32-s3-datasheet.pdf |
| RP2040 | Microcontroller | ACTIVE | rp2040-datasheet.pdf |
| STM32H743ZIT6 | Microcontroller | ACTIVE | stm32h7-datasheet.pdf |
| BCM57508 | Network | ACTIVE | broadcom-bcm57508-datasheet.pdf |
| E810-CQDA2 | Network | DISCONTINUED | Intel_E810_100GbE_NIC.pdf |
| MCX75310AAS-NEAT | Network | ACTIVE | NVIDIA_ConnectX-7_400GbE_SmartNIC.pdf |
| IR3555MTRPBF | Power | EOL | ir3555-datasheet.pdf |
| TPS65982AB | Power | ACTIVE | tps65982-datasheet.pdf |
| BME680 | Sensor | ACTIVE | bme680-datasheet.pdf |
| MPU-6050 | Sensor | DISCONTINUED | mpu6050-datasheet.pdf |
| MZ-V9P2T0 | Storage | ACTIVE | samsung-990pro-datasheet.pdf |
| WUS4C6464DSP3X5 | Storage | DISCONTINUED | wd-ultrastar-dc-sn860.pdf |

## Discrepancias y riesgos detectados

1. **Ruta:** el plan inicial pedía `datos/pdfs/`; se mantiene `data/raw/` porque el bundle de Databricks ya depende de ella.
2. **Categorías en inglés** en el catálogo (`Memory`, `Network`, `Power`, `Sensor`, `Storage`, `Microcontroller`); el enum `Category` usa estos valores canónicos y la UI traduce.
3. **Nombres de archivo heterogéneos** (guiones/guiones bajos, mayúsculas, sufijos `-data`, `-trm`); el join no puede basarse en el nombre del archivo: usar título del datasheet + rapidfuzz contra part number y descripción.
4. **Datasheets de familia** (EPYC 9004, Agilex 7, iCE40, Artix-7, SAM D21): las specs pueden no ser del part number exacto → `Evidence` debe marcar `scope=family`.
5. **NRND sin precio:** XC7A200T (stock 500, fecha desc. 2025-03-01), A100 (stock 12), Cortex-A78 (stock `-`). Precio solo en ACTIVE, consistente con la nota del catálogo; NRND va a `risky_options`.
6. **Cortex-A78 es un IP core** (TRM), no un componente comprable; categoría CPU en el catálogo. Tratar como caso especial en compatibilidad.
7. **Descripción de familia en catálogo:** USB-2627 aparece como "USB-2600 Series Multifunction DAQ".
8. **Celdas multilínea en el catálogo** (fabricante "Measurement Computing (MCC)" partido en 3 líneas con `-layout`): el parser de tablas debe manejar celdas envueltas; validar contra 32 filas esperadas.
9. Los datasheets parecen documentos preparados para el reto (1 página, estructura homogénea): no asumir que reflejan las fichas oficiales completas de los fabricantes.

## Contradicciones dentro de los datasheets (detectadas al construir `spec_registry.yaml`)

La extracción da precedencia al bloque **Key Specifications Summary** y cita literalmente su origen; estas
diferencias con la prosa del mismo PDF no se resuelven automáticamente y conviene mencionarlas en la demo:

| Producto | Prosa | Resumen (valor extraído) |
|---|---|---|
| WUS4C6464DSP3X5 (SN860) | seq. read 6.4 GB/s, write 3.4 GB/s | `seq_read: 7100MBs`, `seq_write: 3900MBs` |
| IR3555MTRPBF | Vin 4.5–15 V, Vout 0.25–3.3 V | `vin: 5-12V`, `vout: 0.25-1.52V` |
| AGFB014R24A (Agilex 7) | 96 transceivers, 58 Gbps PAM4, PCIe Gen4 | `transceivers: 72`, `speed: 116Gbps`, `pcie5: yes` |
| BCM57508 | SR-IOV hasta 1,024 VFs | `sriov: 512VFs` |

Otras observaciones de extracción:
- Los avisos de descontinuación/migración describen **otros** productos (p. ej. el aviso de la E810 habla del IPsec/TLS
  de la ConnectX-7). Esas secciones se excluyen como fuente de specs del propio producto y se reservan para aristas
  `MIGRATES_TO` del grafo.
- La E810 **no** declara offload de IPsec en su datasheet; la ConnectX-7 y la BCM57508 sí.
- RP2040: `I2S` aparece solo como ejemplo de lo implementable con PIO (la cita lo muestra).
- Datasheets sin cabecera `Part Number`/`Manufacturer`/`Category` (E810, A100, ConnectX-7, USB-2627): la identidad
  se toma del catálogo en `join_catalog` (A100 → `A100-SXM4-80GB` por prefijo).
