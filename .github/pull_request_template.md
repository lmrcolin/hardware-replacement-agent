## Qué cambia
<!-- Resumen en 1-3 líneas. Título en Conventional Commits: feat(compatibility): ... -->

## Backlog
<!-- B-xx -->

## Tipo
- [ ] feat
- [ ] fix
- [ ] test
- [ ] docs / chore / build
- [ ] **contract-change** (toca `src/advisor/models/` o una firma de `docs/MODULE_CONTRACTS.md`; requiere aprobación de los 3 devs y bump de `CONTRACT_VERSION`)

## Checklist
- [ ] `make check` verde (contratos + import-linter + tests)
- [ ] Quité el `xfail` de los tests de stub que este PR implementa
- [ ] No hay secretos, tokens ni rutas personales
- [ ] No invento specs, estados ni precios; el catálogo es la fuente de verdad
- [ ] Solo toqué módulos de los que soy dueño (o el dueño revisa este PR)
- [ ] Consultas Databricks acotadas e idempotentes (si aplica)

## Cómo probarlo
<!-- comandos -->
