---
name: hardware-compatibility
description: Use when designing, implementing, reviewing or explaining compatibility rules between industrial components (electrical ratings, signals, protocols, mechanical fit, connectors, materials, pressure, temperature, certifications, installation constraints) or when classifying a replacement as confirmed, conditional, unknown or incompatible.
---

# Compatibilidad de Hardware Industrial

## Regla de oro

**Nunca declares compatibles dos piezas por similitud semántica, de nombre o de descripción.**
La compatibilidad se demuestra atributo por atributo, con unidades y con evidencia citada.
Si falta un dato crítico, el resultado es `UNKNOWN`, no `CONFIRMED`.

## Veredictos

| Veredicto | Condición | Cómo se presenta |
|---|---|---|
| `CONFIRMED` | Todos los HARD coinciden o están dentro de tolerancia, con evidencia | "Sustituto directo según la documentación citada" |
| `CONDITIONAL` | HARD ok, pero hay SOFT en desacuerdo o requisitos de instalación (adaptador, recalibración, firmware, cambio de configuración) | "Posible sustituto si se cumplen: …" |
| `UNKNOWN` | Algún HARD sin dato o sin evidencia | "No se puede confirmar; faltan: …" |
| `INCOMPATIBLE` | Algún HARD en desacuerdo | Descartado de la recomendación directa; se explica el motivo |

Precedencia: `INCOMPATIBLE` > `UNKNOWN` > `CONDITIONAL` > `CONFIRMED`. El ranking ordena **dentro** de un veredicto; nunca lo mejora.

## Clasificación de restricciones

- **HARD:** su incumplimiento puede causar daño, fallo funcional o incumplimiento normativo. También lo es cualquier atributo que el usuario pida "conservar".
- **SOFT:** diferencia tolerable con acción (adaptador, reconfiguración, derating).
- **PREFERENCE:** coste, plazo, fabricante, huella. Solo afectan al ranking.
- **MISSING:** el dato no existe en la fuente. Se informa siempre; nunca se rellena por analogía.

## Cómo comparar cada familia de atributos

| Atributo | Tipo de comparación | Típicamente | Detalles |
|---|---|---|---|
| Tensión de alimentación | rango del candidato ⊇ rango requerido | HARD | AC vs DC es mismatch aunque el número coincida |
| Corriente / potencia consumida | candidato ≤ capacidad disponible de la fuente/lazo | HARD | Comprueba también la corriente de arranque si existe |
| Capacidad de salida (relé, contacto) | candidato ≥ original | HARD | Mira la carga (resistiva/inductiva) y AC/DC |
| Señal analógica | igualdad exacta del tipo (4–20 mA, 0–10 V, 1–5 V) | HARD | 2 hilos vs 4 hilos; activa vs pasiva; HART |
| Señal digital | tipo (NPN/PNP, contacto seco), nivel lógico | HARD | |
| Protocolo de comunicación | igualdad + versión/perfil (HART 5/7, Modbus RTU/TCP, PROFIBUS PA/DP, FOUNDATION Fieldbus, EtherNet/IP) | HARD | Mismo nombre ≠ mismo perfil; revisa el DD/GSD/EDS |
| Conector / conexión a proceso | estándar + tamaño + rosca (NPT ½", G ½, M20×1.5, brida ASME B16.5 Clase 150 …) | HARD | Una rosca diferente obliga a adaptador → como mínimo CONDITIONAL |
| Conexión eléctrica / prensaestopas | rosca de entrada (½" NPT vs M20) | SOFT | Adaptador certificado si hay zona clasificada |
| Dimensiones / montaje | envolvente ≤ espacio disponible; patrón de montaje igual | HARD/SOFT | Se requiere el dato de espacio disponible, si no → UNKNOWN |
| Materiales en contacto con proceso | compatibilidad química con el fluido (316L, Hastelloy C-276, PTFE…) | HARD | Material "mejor" no siempre es compatible (p. ej. con cloruros, H₂S → NACE MR0175) |
| Presión | rango del candidato ⊇ rango de operación; MWP/presión de prueba ≥ original | HARD | Absoluta vs manométrica (bar a vs bar g) |
| Temperatura (proceso y ambiente) | rango del candidato ⊇ rango requerido | HARD | Separa temperatura de proceso, ambiente y de almacenamiento |
| Precisión / rango ajustable | candidato igual o mejor; turndown suficiente | SOFT | |
| Certificaciones | conjunto requerido ⊆ conjunto del candidato | HARD | ATEX/IECEx zona y grupo de gas, clase T, Class I Div 1/2, SIL, IP/NEMA, CE, UL |
| Restricciones de instalación | orientación, tramos rectos, alimentación separada | SOFT | Se convierten en condiciones explícitas |

## Unidades y tolerancias

- Normaliza a SI antes de comparar (bar→Pa, °F→°C/K, in→mm). Conserva el valor y unidad originales para la cita.
- Nunca compares magnitudes de dimensión diferente; un error de unidad equivale a `MISSING`, no a `MATCH`.
- Las tolerancias se aplican sobre el valor requerido: `|candidato − requerido| ≤ tolerancia_abs` o `≤ tolerancia_rel × requerido`. Una tolerancia ausente equivale a igualdad estricta.
- Para rangos: `cand.min ≤ req.min` y `cand.max ≥ req.max` (contención), no solapamiento.

## Ejemplo de evaluación

Original `SYN-PT-100` (sintético): 4–20 mA HART 7, 10.5–42.4 V DC, 0–10 bar g, ½" NPT, 316L, ATEX II 1 G Ex ia IIC T4.

| Candidato | Hallazgo | Veredicto |
|---|---|---|
| `SYN-PT-200` | todo igual; rango 0–16 bar g ⊇ 0–10 | CONFIRMED |
| `SYN-PT-210` | igual pero conexión G ½ | CONDITIONAL (adaptador certificado ½" NPT↔G ½) |
| `SYN-PT-220` | sin dato de certificación ATEX | UNKNOWN (falta certificación) |
| `SYN-PT-300` | salida 0–10 V | INCOMPATIBLE (tipo de señal) |

## Explicación obligatoria por candidato

1. Atributos coincidentes (con valor y fuente).
2. Diferencias y su clasificación (HARD/SOFT/PREFERENCE).
3. Condiciones necesarias para la instalación.
4. Información desconocida.
5. Evidencias: `document_id`, página, `chunk_id`.

## Errores a evitar

- "Mismo fabricante/familia/serie → compatible".
- Tratar un atributo ausente como igual al original.
- Comparar números sin unidades, o bar g con bar a.
- Considerar "mejor" siempre compatible (más presión ≠ mismo rango calibrado; otro material puede reaccionar con el fluido).
- Ocultar un mismatch HARD porque el score global es alto.
- Inventar equivalencias de normas o certificaciones.
