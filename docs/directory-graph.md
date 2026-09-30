# Grafo de directorios

El motor recibe un directorio y construye un NetworkX MultiDiGraph con archivos como nodos e imports como aristas dirigidas: importador → dependencia. Primero genera CST reales con Tree-sitter para Python, JavaScript y TypeScript, incluidos JSX y TSX. Nunca ejecuta los archivos analizados.

## Comandos

```bash
.venv/bin/safecode-graph examples/graph-demo --format html --output reports/graph-demo.html
.venv/bin/safecode-graph examples/graph-demo --include-cst --output /tmp/graph.json
.venv/bin/safecode-graph examples/graph-demo --subgraph frontend/shared
.venv/bin/safecode-graph /ruta/proyecto --python-root src --alias @/=frontend/
```

El HTML se abre directamente en el navegador y funciona sin Internet. Permite seleccionar carpetas, archivos y evidencia CST; muestra relaciones de frontera y referencias pendientes. Es un snapshot: regenerar después de editar archivos.

## API

```python
from safecode_core.directory_graph import DirectoryGraphEngine
result = DirectoryGraphEngine('/ruta/proyecto').analyze()
report = result.to_dict()
graph = result.graph
subgraph = result.subgraph('frontend')
subreport = result.to_dict('frontend')
consumers = result.affected_by('frontend/shared/types.ts')
```

Cada carpeta, incluso vacía, define un subgrafo inducido por sus archivos y descendientes. Compartir carpeta no crea dependencias. La exportación conserva boundary_edges y boundary_nodes para relaciones que cruzan la carpeta seleccionada. El selector conserva la jerarquía completa. El visor muestra un mapa de relaciones directas del archivo seleccionado: consumidores entrantes, archivo central y dependencias salientes. Agrupa referencias repetidas por archivo, permite búsqueda y pagina cada lado en grupos de ocho. Seleccionar una tarjeta centra el mapa en ese archivo, incluso si está fuera de la carpeta. En paneles estrechos los bloques se apilan sin reducir el texto. No muestra simultáneamente todas las aristas del proyecto; el grafo completo permanece en el JSON.

JSON contiene nodes, edges, directories, references, issues, excluded, isolated_files, cyclic_components y metrics. Las referencias incluyen identificador, tipo, rango y texto del nodo CST. Líneas desde 1, columnas de bytes UTF-8 desde 0 y extremo final exclusivo. --include-cst incorpora árboles completos y código fuente; por defecto solo se conserva evidencia y resúmenes. Los informes deben tratarse con los mismos permisos que el código.

## Resolución y límites

- Python: import, from, aliases y referencias relativas con raíces configurables. Resuelve módulos o submódulos locales, no verifica símbolos exportados ni modela la ejecución de __init__.py.
- JS/TS: imports, reexports, import() literal, require() directo e import=require. Rutas relativas, índices, sustitución de extensiones TypeScript y aliases explícitos. Múltiples candidatos quedan ambiguos; no se simula precedencia de un bundler.
- No se replica la resolución completa de Node, tsconfig, package.json exports o workspaces. Los bindings de require e importlib pueden estar redefinidos. No se detectan todas las referencias dinámicas, llamadas HTTP o accesos a archivos en ejecución.
- Los archivos de otros formatos son nodos sin parser. Se puede resolver un import de CSS existente, pero no extraer sus dependencias internas.
- Un archivo aislado carece de aristas locales dentro de la selección; puede tener relaciones de frontera o referencias externas. Ausencia de arista no demuestra independencia.
- status=partial indica errores o referencias no resueltas localmente, incluidas bibliotecas externas normales. Estas referencias se conservan explícitamente; no se inventan destinos.
- Se excluyen enlaces simbólicos, archivos y carpetas ocultos, node_modules, entornos virtuales y carpetas de compilación habituales. Se registran las exclusiones; no se interpreta .gitignore.
- Límites: 2.000 archivos, 1 MB y 200.000 nodos por archivo, 20 MB acumulados de código analizado. Solo UTF-8. Las carpetas masivas deben analizarse por raíces menores; el layout inicial no está optimizado para miles de nodos.
- Cada análisis reconstruye el snapshot. No hay watcher ni actualización incremental con Tree.edit. El CST verifica estructura sintáctica, no tipos, seguridad ni comportamiento.

El comando anterior safecode-core conserva su implementación Python. Para el recorrido multilenguaje usar safecode-graph. Las pruebas nuevas cubren evidencia exacta, los tres lenguajes, subgrafos, fronteras, ciclos, cambios de archivos, ambigüedad, errores, límites y exportación HTML segura.
