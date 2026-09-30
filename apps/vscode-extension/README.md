# SafeCode Studio para VS Code

La extensión añade el icono **SafeCode** a la barra de actividad con un resumen, el explorador de archivos y relaciones, el grafo interactivo y hallazgos agrupados por regla. Al analizar o guardar un archivo compatible, consulta el Core Engine local por JSON-RPC. Los hallazgos se muestran en **Problemas** y en el editor; al seleccionar uno se abre un panel lateral con explicación, evidencia y dependencias relacionadas.

## Instalar el paquete local

En VS Code, abra **Extensiones** → menú `…` → **Install from VSIX…** y seleccione `dist/safecode-studio-0.1.3.vsix` desde la raíz del repositorio SafeCode. Abra después el proyecto que quiere analizar. Para `menasa`, la extensión detecta el entorno virtual de SafeCode en la carpeta hermana. Si no lo encuentra, use **SafeCode: Elegir Python** y seleccione `/home/snow/Desktop/Projects/SafeCode/.venv/bin/python`. El VSIX incluye el código del Core Engine; el intérprete debe tener instaladas sus dependencias Python.

## Idioma de la extensión

En el resumen de SafeCode, pulse **Idioma / Language** y elija **Español**, **English** o **Automático**. También puede usar el comando **SafeCode: Elegir idioma** o la opción `safecode.language` en Configuración. El idioma automático sigue el idioma de VS Code. La preferencia cambia inmediatamente el resumen, el árbol, el grafo, los hallazgos, los mensajes, los diagnósticos y los reportes HTML exportados; no repite el análisis.

VS Code traduce los nombres del menú de comandos y las descripciones de Configuración según el idioma del propio editor. La opción de SafeCode controla las vistas y resultados de la extensión, aunque el editor use otro idioma.

En VS Code Flatpak, la extensión ejecuta ese Python en el host mediante `flatpak-spawn --host`. Ejecutar la ruta del entorno virtual directamente dentro de Flatpak puede cargar otra versión de Python y ocultar sus paquetes, que fue la causa del error `No module named 'tree_sitter'`.

## Ejecutar durante el desarrollo

1. Abra `/home/snow/Desktop/Projects/SafeCode/apps/vscode-extension` en VS Code.
2. Ejecute `npm install` y `npm run build` en esa carpeta.
3. Pulse **F5** para abrir una ventana *Extension Development Host* y abra allí el proyecto que desea analizar.
4. En la barra lateral, abra **SafeCode** y ejecute **SafeCode: Analizar proyecto**. Puede elegir otra carpeta abierta con **SafeCode: Elegir carpeta abierta**.

El build copia el paquete Python del core dentro de `python/`, para que la extensión pueda invocarlo aunque no esté instalado de forma editable. El Python elegido debe tener instalados `tree-sitter`, sus gramáticas y `networkx` según `packages/core/pyproject.toml`. Durante el desarrollo, la extensión detecta automáticamente `.venv` en la raíz de SafeCode. Si usa otra instalación, configure `safecode.pythonPath` con la ruta a su intérprete.

Si inicia la extensión desde este repositorio, el proyecto de ejemplo `examples/security-demo/current` permite ver las cinco familias. Configure `safecode.baselinePath` con la ruta a `examples/security-demo/baseline` y `safecode.policyPath` con `examples/security-demo/policy.json` antes del análisis para activar las dos reglas de arquitectura. Estas rutas pueden ser absolutas o relativas a la carpeta abierta.

## Comportamiento

- La barra lateral muestra carpetas, archivos, a quién importa cada archivo y quiénes lo importan. Los archivos con errores tienen icono rojo; los de advertencia, ámbar. Cada carpeta que contiene hallazgos, incluso en subcarpetas, muestra una insignia pequeña con la severidad más alta y el total de hallazgos. Al resolverlos en un nuevo análisis, desaparece la insignia. El menú contextual **Mostrar en grafo** centra el archivo en el visor HTML existente.
- **Hallazgos** agrupa SEG-01/02/03 y ARQ-01/02. Seleccionar un hallazgo abre la línea correspondiente y un panel de detalle junto al editor.
- El resumen permite analizar, elegir Python y exportar un reporte HTML con las reglas ejecutadas y la evidencia de cada hallazgo.
- Los diagnósticos de `SafeCode` aparecen en **Problemas** y en el editor, como los de un linter. SEG-01 y SEG-02 se publican como errores; SEG-03 y las reglas de arquitectura como advertencias. La colección se sustituye en cada análisis; los hallazgos resueltos desaparecen.
- Guardar un archivo de la carpeta seleccionada provoca un análisis nuevo si `safecode.analyzeOnSave` está activado. Las respuestas viejas se descartan según la versión de la sesión.
- Si faltan la base o la política, las reglas ARQ correspondientes figuran como omitidas. Un fallo del proceso se muestra como error y no como un análisis limpio.

La integración usa la API nativa `DiagnosticCollection` de VS Code. ESLint se limita a JavaScript/TypeScript y no puede representar por sí solo las reglas Python o de grafo; SafeCode publica diagnósticos propios para las cinco familias, sin duplicar reglas en otro motor. Puede utilizarse junto a la extensión ESLint habitual.

## Límites actuales

La extensión analiza el contenido **guardado en disco**. No inspecciona cambios aún no guardados, no ofrece correcciones automáticas y no ejecuta IA. La primera indexación recorre el directorio completo; las posteriores reutilizan CST de archivos sin cambios. El motor no observa el sistema de archivos por sí mismo: la extensión actualiza al guardar o al usar el comando. El panel de detalle sigue el diseño del mockup para las capacidades ya implementadas; confianza probabilística y modelos IA todavía no forman parte del motor. No se ha validado en Windows.
