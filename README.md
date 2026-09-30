# SafeCode Studio

Motor local con una etapa independiente de Tree-sitter para Python, JavaScript y TypeScript. Recibe una ruta de archivo y devuelve su CST sin ejecutar código. El nuevo motor de NetworkX analiza directorios en los tres lenguajes y exporta JSON o un visor HTML local.

## Grafo multilenguaje

```bash
.venv/bin/safecode-graph examples/graph-demo --format html --output reports/graph-demo.html
.venv/bin/safecode-graph examples/graph-demo --subgraph frontend --include-cst
```

[API, subgrafos y límites](docs/directory-graph.md).

## Sesión incremental del Core Engine

El motor persistente reutiliza CST y hallazgos de archivos intactos, actualiza las relaciones cambiadas y entrega diferencias versionadas del grafo. Expone una API Python y un proceso local JSON-RPC por líneas:

```bash
.venv/bin/python -m safecode_core.workspace_cli /ruta/proyecto --baseline /ruta/version-base --policy /ruta/policy.json
```

[Contrato, ejemplo de solicitud y límites](docs/incremental-workspace.md).

## Análisis determinista de seguridad y arquitectura

```bash
.venv/bin/python -m safecode_core.security_cli examples/graph-demo --format html --output reports/security-demo.html
.venv/bin/python -m safecode_core.security_cli proyecto-actual --baseline proyecto-base --policy policy.json --format json --output reports/security.json
```

El informe reúne hallazgos con evidencia del CST, cobertura y límites del análisis. Las tres reglas de seguridad se ejecutan en el directorio actual; los ciclos nuevos y las dependencias prohibidas requieren una versión base, y la última también una política explícita. [Catálogo, ejemplos y formato del reporte](docs/security-analysis.md).

## Analizar archivos manualmente

```bash
cd /home/snow/Desktop/Projects/SafeCode
.venv/bin/safecode-cst examples/cst/python/basics.py --format tree
.venv/bin/safecode-cst examples/cst/javascript/basics.js --format tree
.venv/bin/safecode-cst examples/cst/typescript/basics.ts --format tree
.venv/bin/safecode-cst examples/cst/typescript/card.tsx > /tmp/card-cst.json
.venv/bin/safecode-cst --stdio
```

[Guía completa, ejemplos y mini aplicaciones](docs/tree-sitter-manual.md).

## Instalación y grafo Python existente

Desde `/home/snow/Desktop/Projects/SafeCode`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'packages/core[dev]'
.venv/bin/python -m pytest packages/core
.venv/bin/safecode-core tests/fixtures/python_demo
.venv/bin/safecode-core tests/fixtures/python_demo --affected app/repository.py
.venv/bin/safecode-core tests/fixtures/python_demo --cst app/service.py
```

La CLI escribe JSON a stdout. Puede redirigirse a un archivo local. Los informes y CST contienen fragmentos del código analizado: tratarlos con los mismos permisos que el repositorio.

## Implementado

- Descubrimiento de archivos Python UTF-8 con rutas relativas y límites de tamaño.
- CST reales, hashes, errores y tokens ausentes; funciones, clases y anidamiento.
- Grafo `MultiDiGraph` con relaciones `contains` e `imports` respaldadas por evidencia del CST.
- Importaciones absolutas, relativas, aliases y raíces de código configurables.
- Registro de importaciones externas/no resueltas, ambiguas y algunos patrones dinámicos.
- Componentes cíclicas y consulta de consumidores transitivos de un archivo.
- Caché de parsing por contenido en la API de larga duración; reconstrucción del grafo en cada análisis para evitar relaciones obsoletas.
- CLI, fixture demostrativo y pruebas automatizadas.

## Alcance actual

El CST verifica la estructura sintáctica, no demuestra seguridad ni corrección del programa. Se resuelven dependencias de módulos, no valores ni llamadas. `from module import name` solo verifica el módulo o submódulo resoluble, no que un símbolo exportado exista. Las importaciones se consideran dependencias potenciales aunque estén dentro de condiciones o funciones.

La extensión de VS Code, IA y actualización incremental dentro de un archivo mediante `Tree.edit` todavía no están implementadas. La sesión incremental por archivo y el proceso local JSON-RPC sí están disponibles. Las reglas deterministas iniciales tienen cobertura acotada a patrones explícitos. Python 3.14 fue probado en este equipo; Python 3.11 es el mínimo declarado y requiere su propia validación antes de publicar.

Más detalles: [arquitectura del core](docs/core-engine.md).
