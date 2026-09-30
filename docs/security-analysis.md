# Análisis determinista del catálogo inicial

El comando `safecode-security` analiza un directorio sin ejecutar el código. Usa los nodos, rangos y estados del CST de Tree-sitter para ubicar patrones y el grafo de NetworkX para comparar dependencias con una versión base. Produce un HTML legible o JSON para integración futura con VS Code.

```bash
.venv/bin/python -m safecode_core.security_cli examples/graph-demo --format html --output reports/security-demo.html
.venv/bin/python -m safecode_core.security_cli proyecto-actual --baseline proyecto-base --policy policy.json --format json --output reports/security.json
```

Para reproducir un informe con las cinco familias, use `examples/security-demo/current` como proyecto, `examples/security-demo/baseline` como base y `examples/security-demo/policy.json` como política. El resultado verificado está en `reports/security-demo.html` y `reports/security-demo.json`: seis hallazgos, sin incidencias de análisis.

Tras reinstalar el paquete en modo editable, también está disponible `.venv/bin/safecode-security` con los mismos argumentos.

La política usa rutas relativas al directorio analizado. Por ejemplo:

```json
{
  "forbidden": [
    {"from": "ui/*", "to": "data/*"}
  ]
}
```

Las cinco familias del documento son:

| ID | Qué detecta | Condición de evaluación |
| --- | --- | --- |
| SEG-01 | SQL construido con entrada externa e introducido en `execute`, `executemany`, `query` o `raw` | Python, JS y TS; asignaciones locales y expresiones directas |
| SEG-02 | Comando construido con entrada externa y ejecutado mediante shell | `subprocess` con `shell=True`, `os.system`, `exec`/`execSync`, `spawn`/`spawnSync` con `shell: true` |
| SEG-03 | Literal en variable cuyo nombre señala credencial | Python, JS y TS; el valor se omite del informe |
| ARQ-01 | Componente cíclica nueva causada por una arista añadida | Requiere `--baseline` |
| ARQ-02 | Importación nueva que viola un patrón de rutas prohibido | Requiere `--baseline` y `--policy` |

El HTML muestra cada hallazgo con archivo, línea, regla, explicación y evidencia. El JSON conserva el identificador y tipo del nodo CST, rango, hash del archivo, cobertura por regla, incidencias y exclusiones. `status=partial` indica que alguna regla se omitió o hubo archivos con problemas de análisis. Ningún estado ni ausencia de hallazgos acredita seguridad del proyecto.

La batería de pruebas en `packages/core/tests/test_security.py` incluye interpolación, concatenación y formato de SQL; ejecución de comandos mediante distintas APIs; secretos sintéticos en los tres lenguajes; consultas parametrizadas, uso de argumentos separados, valores de entorno y placeholders que no deben alertar; y cambios de arquitectura positivos y preexistentes. Todos los ejemplos son sintéticos y el motor nunca los ejecuta.

## Límites actuales

- El flujo de datos se restringe a asignaciones y variables dentro de la misma función o módulo. No sigue llamadas entre funciones, aliases de objetos, sanitizadores ni valores de retorno.
- Los adaptadores reconocen solo las fuentes y APIs enumeradas en el código. Una API desconocida o un nombre distinto puede pasar sin detección.
- La regla de credenciales es una heurística léxica. Puede alertar sobre datos de prueba o ignorar claves con nombres no reconocidos. No verifica si una credencial es válida.
- La CLI independiente `safecode-security` compara dos directorios mediante `--baseline`; no obtiene una revisión Git por sí sola.
- La sesión incremental y la extensión de VS Code sí pueden obtener la versión base de un commit Git (`--git-baseline-ref`). La política de capas sigue siendo explícita: el asistente de la extensión ayuda a crearla, pero no la deduce automáticamente.
- Errores sintácticos y archivos excluidos reducen la cobertura. El reporte los enumera, pero no pretende cobertura de autorización, CVEs, flujo interprocedimental o seguridad formal.
