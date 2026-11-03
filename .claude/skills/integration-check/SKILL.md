---
name: integration-check
description: Pre-merge integration checklist for develop→main - runs make check, contract tests, import direction, smoke tests and secret scan, and reports a go/no-go. Invoke manually before merging or before the demo.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Integration check

## Alcance
Verificación, no implementación. No edites código salvo que el usuario lo pida.

## Pasos
1. `git status` limpio y rama correcta (`develop` o PR hacia `main`).
2. `make check` (ruff, import-linter, pytest). Contratos verdes; listar xfail restantes por módulo y backlog (B-xx).
3. `git diff --stat main...HEAD -- src/advisor/models` → si hay cambios, exigir etiqueta `contract-change`.
4. `uv run pre-commit run gitleaks --all-files` → 0 hallazgos.
5. `make pipeline-local` (o confirmar que `artifacts/` existe) y `make eval` si hay agente real.
6. Revisar `scripts/smoke_tests.md` y marcar cada caso.
7. Confirmar invariantes: ninguna recomendación no-ACTIVE; ningún precio en no-ACTIVE; caso E810 correcto.

## Salida
Tabla `paso | resultado | evidencia` y veredicto **GO / NO-GO** con bloqueantes por módulo y backlog.

## Prohibido
Marcar GO con tests rojos, secretos detectados o contratos cambiados sin PR `contract-change`.
