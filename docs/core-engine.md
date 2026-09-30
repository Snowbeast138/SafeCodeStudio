# Core Engine v0.1

## Flujo y dirección

```mermaid
flowchart LR
    F[Archivos Python UTF-8] --> P[Tree-sitter / CST]
    P --> E[Declaraciones e importaciones con evidencia]
    E --> R[Resolución estática de módulos locales]
    R --> G[NetworkX MultiDiGraph]
    G --> J[JSON: grafo, incidencias y ciclos]
```

`file:A -> file:B`, con `relation=imports`, significa que A importa B. Los antecesores de B son sus consumidores potencialmente afectados. `contains` apunta del archivo o declaración contenedora a la declaración hija. Las relaciones se separan al calcular ciclos; la jerarquía de declaraciones no se confunde con dependencias de archivos.

La evidencia incluye tipo de nodo CST, texto, bytes inicial/final y coordenadas. Líneas desde 1, columnas desde 0 en **bytes UTF-8**, final exclusivo. No son columnas UTF-16 de VS Code; el futuro adaptador deberá convertirlas. Los identificadores de símbolos incluyen desplazamiento y no son estables ante movimientos del texto.

## API

```python
from safecode_core import Engine

engine = Engine('/ruta/proyecto', source_roots=('.',))
result = engine.analyze()
print(result.affected_by('app/repository.py'))
print(result.to_dict())
# Tras modificar, renombrar o borrar archivos:
updated = engine.analyze()
```

La caché vive en la instancia del motor. Conserva árboles de archivos cuyo hash no cambia y elimina entradas borradas/no legibles. Archivos cambiados se parsean completos; el grafo se reconstruye. Es una base de corrección para comparar posteriormente con una actualización verdaderamente incremental. Cada ejecución de CLI crea una instancia nueva.

## Resolución conservadora

El directorio raíz es la raíz de importaciones por defecto. Para estructura `src/` usar `--source-root src`; repetir el argumento si hay varias raíces. Las rutas deben permanecer dentro del proyecto. Los módulos con candidatos duplicados se marcan ambiguos en vez de elegir arbitrariamente.

Se soportan módulos `.py`, paquetes `__init__.py`, importaciones relativas y destinos locales dentro de directorios namespace cuando existe un archivo destino. Los paquetes namespace sin archivo propio no reciben nodos sintéticos. No se ejecutan `__init__.py`, hooks ni código para descubrir exportaciones.

`from pkg import item` busca primero un submódulo local y, en su defecto, el módulo base. La arista declara `module_only`: no prueba que `item` exista. No se modelan dependencias implícitas de inicialización de paquetes, reexportaciones, precedencia completa de sys.path, extensiones nativas, import hooks ni asignaciones dinámicas. Importaciones externas y ausentes comparten estado `external_or_missing`, sin afirmar que la dependencia esté instalada o sea inválida. Los patrones dinámicos detectados son solo `__import__` e `importlib.import_module` directos; sus aliases no se rastrean.

## Estados y límites

`partial`: hubo incidencias. `complete_for_supported_scope`: no se observaron incidencias en el alcance limitado; no significa programa seguro. Errores sintácticos se preservan, incluso tokens ausentes anónimos. Archivos no UTF-8 o mayores de 1 MB se reportan sin analizar. Se excluyen directorios ocultos y los directorios de dependencias/build indicados en `EXCLUDED`; no se implementa `.gitignore`. Directorios symlink no se recorren y archivos symlink se reportan y omiten.

Los consumidores calculados reflejan relaciones sintácticas potenciales, no ejecución real. Los ciclos son componentes fuertemente conexas, no una enumeración de todos los caminos cíclicos. No se declara que un ciclo sea nuevo sin comparar contra una versión base.

## Referencias de implementación

- https://tree-sitter.github.io/py-tree-sitter/
- https://github.com/tree-sitter/tree-sitter-python
- https://networkx.org/documentation/stable/reference/classes/multidigraph.html

Las versiones se fijan en `packages/core/pyproject.toml`. La implementación no depende de servicios externos ni transmite código.
