# Sesión persistente e interfaz local del Core Engine

`WorkspaceEngine` mantiene una sesión por directorio. La primera llamada indexa todos los archivos compatibles; las siguientes leen los archivos para comprobar sus hashes, pero solo vuelven a construir el CST y las reglas de los archivos cuyo contenido cambió. Si se agrega, borra o renombra un archivo, las referencias cacheadas se vuelven a resolver de forma conservadora porque un destino antes ausente o ambiguo puede cambiar. El grafo se actualiza en la sesión y se entrega como diferencias.

```python
from safecode_core import WorkspaceEngine

engine = WorkspaceEngine('/ruta/proyecto', baseline='/ruta/version-base', policy='/ruta/policy.json')
# Alternativa sin checkout: git_baseline_ref='HEAD' (no combinar con baseline)
first = engine.update(request_id='scan-1', version=1)
second = engine.update(request_id='scan-2', version=2)  # después de editar archivos
graph = engine.graph_snapshot()  # instantánea completa sin código fuente ni CST
```

`version` es un entero creciente asignado por el cliente a la sesión. Una versión repetida o anterior se rechaza y no sustituye el resultado vigente. El motor no vigila el sistema de archivos: el cliente llama `update` al guardar o cuando desea volver a analizar. Una instancia debe usarse en un único trabajador; el cliente es responsable de no publicar respuestas obsoletas cuando existan solicitudes concurrentes.

La respuesta incluye `schema_version`, `request_id`, `workspace_id`, `version`, `status`, `coverage`, `changes` (`added`, `modified`, `removed`, `renamed`), `graph_delta` (nodos y aristas añadidos, actualizados o eliminados), `reference_delta` (importaciones resueltas, pendientes o eliminadas), `findings`, `findings_delta` (nuevos y resueltos), `issues`, `excluded` y `metrics` (`parsed_files`, `reused_files`, `re_resolved_files`). Los rangos de hallazgos son líneas desde 1 y columnas en bytes UTF-8 desde 0; el adaptador de VS Code tendrá que convertirlos a UTF-16. Los identificadores de hallazgo se derivan de regla, ubicación y evidencia; una reubicación se presenta como resuelto y nuevo.

El proceso local usa JSON-RPC 2.0, una solicitud JSON por línea de entrada estándar y una respuesta JSON por línea de salida estándar:

```bash
.venv/bin/python -m safecode_core.workspace_cli /ruta/proyecto --baseline /ruta/version-base --policy /ruta/policy.json
.venv/bin/python -m safecode_core.workspace_cli /ruta/proyecto --git-baseline-ref HEAD --policy /ruta/policy.json
```

Solicitud de análisis: `{"jsonrpc":"2.0","id":"scan-1","method":"analyze","params":{"version":1}}`. También acepta `graph` con `params.directory` opcional para obtener una instantánea sin CST ni texto fuente, y `shutdown` para cerrar. El proceso responde con errores JSON-RPC recuperables por solicitud y no escribe registros en stdout. Cada línea se limita a 1 MB.

Las reglas SEG-01/02/03 usan el CST de cada archivo cambiado. ARQ-01/02 comparan el grafo vigente con una instantánea base fija proporcionada al iniciar la sesión. Sin base o política, las reglas correspondientes constan como omitidas y el estado es `partial`; un resultado sin hallazgos no prueba seguridad. La política y la base no se cambian durante una sesión: para modificarlas se crea otra instancia.

La base puede provenir de un directorio o de una revisión Git, nunca de ambas a la vez. Para Git, se resuelve la referencia a un commit, se lee su árbol sin alterar el directorio de trabajo y se compara con los archivos actuales; la respuesta incluye `baseline` con referencia y commit exacto. No se extraen symlinks. La lectura está limitada a 20 000 entradas y 50 MB de código fuente materializado. El archivo de política de capas sigue siendo explícito y es necesario para ARQ-02. Si la revisión o la política cambian, reinicie la sesión.

## Verificación y límites

Las pruebas comparan el resultado estructural después de edición, alta, borrado y renombre con una reconstrucción completa. Verifican que la edición de un archivo solo repase y resuelva ese archivo, que la aparición de un destino actualice importaciones previas, que errores sintácticos se recuperen y que la respuesta JSON-RPC conserve versiones y errores.

Este hito incrementa por archivo, no aplica `Tree.edit` dentro de un archivo. El descubrimiento y cálculo de hashes aún recorren el directorio; ante cambios en el conjunto de archivos se re-resuelven todas las referencias cacheadas para asegurar corrección. Tampoco hay watcher, cliente de VS Code, selección de contexto por presupuesto ni inferencia. El rendimiento p95, uso de memoria y portabilidad siguen pendientes de medición.
