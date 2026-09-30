# Laboratorio manual: archivo → CST

## Qué está implementado

`CSTService` recibe una ruta de archivo, detecta la gramática por extensión y devuelve un CST obtenido directamente de Tree-sitter. Esta ruta no construye grafos ni importa NetworkX. Python, JavaScript y TypeScript son lenguajes; TSX y JSX son variantes sintácticas, no modelos de IA.

Extensiones: `.py`; `.js`, `.mjs`, `.cjs`, `.jsx`; `.ts`, `.mts`, `.cts`, `.tsx`. JavaScript utiliza la gramática que incluye JSX; `.tsx` selecciona la gramática TSX independiente. UTF-8 únicamente. No se requiere instalar las dependencias del código inspeccionado ni ejecutar el archivo.

## Comandos desde el repositorio

```bash
cd /home/snow/Desktop/Projects/SafeCode

# Árbol legible en terminal
.venv/bin/safecode-cst examples/cst/python/basics.py --format tree
.venv/bin/safecode-cst examples/cst/javascript/basics.js --format tree
.venv/bin/safecode-cst examples/cst/typescript/basics.ts --format tree

# JSON completo, con código fuente, metadatos y nodos
.venv/bin/safecode-cst examples/cst/typescript/card.tsx > /tmp/card-cst.json

# Recuperación ante sintaxis incompleta
.venv/bin/safecode-cst examples/cst/python/broken.py --format tree
.venv/bin/safecode-cst examples/cst/javascript/broken.js --format tree
.venv/bin/safecode-cst examples/cst/typescript/broken.ts --format tree

# Diferencia entre sintaxis y tipos: devuelve parsed aunque el tipo es incorrecto
.venv/bin/safecode-cst examples/cst/typescript/type_error.ts
```

También se aceptan rutas absolutas. `--language python|javascript|typescript|tsx` permite seleccionar una gramática explícita. No se soportan HTML, archivos Vue/Svelte ni scripts embebidos en HTML.

## Motor que espera rutas

```bash
.venv/bin/safecode-cst --stdio
```

Escribir una solicitud JSON por línea y pulsar Enter:

```json
{"id":"python-1","path":"examples/cst/python/basics.py"}
{"id":"js-1","path":"examples/cst/javascript/server.mjs"}
{"id":"ts-1","path":"examples/cst/typescript/server.ts"}
```

Cada respuesta ocupa una línea JSON e incluye el mismo `id` y `result` o `error`. El proceso espera la siguiente solicitud, reutiliza las gramáticas y vuelve a leer el archivo; termina al cerrar stdin (Ctrl+D en Linux). Es un protocolo JSON Lines propio, no JSON-RPC. Se procesa secuencialmente. Una solicitud malformada no termina la sesión. El proceso puede leer archivos accesibles para el usuario que lo inicia; no exponerlo como servidor remoto sin un control de acceso y raíz permitida.

## Leer el CST

El JSON usa una representación por adyacencia: `root_id` apunta al nodo raíz de `nodes`; cada nodo tiene `id`, `parent`, `children` y `field`. No es un resumen ni un grafo de dependencias: conserva todos los nodos y su orden, incluyendo tokens anónimos, comentarios, nodos ERROR y tokens missing. La forma plana evita límites de recursión al serializar árboles profundos.

- `type`: tipo de nodo según la gramática; raíz `module` en Python y `program` en JS/TS.
- `named`: distingue nodos con nombre de tokens como `(`, `;` o palabras clave.
- `field`: función del hijo dentro del padre, por ejemplo `name`, `body` o `parameters`.
- `extra`: elementos extra de la gramática, como comentarios.
- `start_byte`, `end_byte`: rango sobre `source.encode('utf-8')`, con final exclusivo.
- Coordenadas: líneas desde 1 y columnas desde 0 en bytes UTF-8, no caracteres ni UTF-16.
- `error`, `missing`, `has_error`: fallo explícito, token esperado ausente o error en el subárbol.

El código fuente se conserva una sola vez. Para recuperar el texto de un nodo:

```python
from safecode_core import CSTService

service = CSTService()
report = service.parse_file('examples/cst/typescript/basics.ts')
raw = report['source'].encode('utf-8')
for node in report['nodes']:
    if node['type'] == 'interface_declaration':
        print(raw[node['start_byte']:node['end_byte']].decode('utf-8'))
```

`status=parsed` significa que esta gramática no reportó errores sintácticos; no acredita tipos, importaciones válidas, seguridad ni corrección en ejecución. `syntax_errors` sigue entregando el árbol recuperado. Ambos estados son resultados de parsing y devuelven exit code 0. Archivos ausentes, extensión no soportada y otros errores operativos devuelven código 2 y JSON en stderr.

## Ejemplos disponibles

Cada lenguaje incluye `basics`, `broken` y un pequeño servidor web. Además hay JSX, TSX y un error de tipos intencional. Los archivos `broken` no deben ejecutarse: sirven para observar recuperación sintáctica.

Servidores opcionales en terminales independientes:

```bash
python3 examples/cst/python/server.py
node examples/cst/javascript/server.mjs
node --experimental-strip-types examples/cst/typescript/server.ts
```

Abrir respectivamente `http://127.0.0.1:8101`, `http://127.0.0.1:8102` y `http://127.0.0.1:8103`. Cada página enlaza `/api/status`. Detener con Ctrl+C. El ejemplo TS requiere Node con soporte de eliminación de tipos (probado en Node 22 del equipo); no se realiza type-checking. JSX/TSX son muestras de parsing, no aplicaciones React instaladas.

Mientras un servidor corre, analizar su archivo con `safecode-cst` en otra terminal. Modificar una función, guardar y repetir el comando o solicitud JSONL; comparar `sha256`, nodos y rangos. Ejecutar el servidor es independiente: Tree-sitter nunca lo inicia ni necesita que esté corriendo.

## Límites y rendimiento

Hasta 1 MB de fuente y 200 000 nodos por solicitud por defecto; configurables en la API. Al superar un límite se devuelve un error, no un árbol silenciosamente truncado. Sin límite de tiempo garantizado. `parse_ms` mide solo parsing; `parse_and_extract_ms` añade extracción pero excluye lectura, carga inicial de gramática, serialización JSON y salida a terminal. Los archivos cambiados se parsean completos; no se implementa todavía `Tree.edit`, watch ni análisis de tipos. Una instancia de servicio es secuencial, no compartible concurrentemente sin coordinación.

Los reportes contienen el código fuente completo; conservarlos como material del repositorio. No se envían a servicios externos.
