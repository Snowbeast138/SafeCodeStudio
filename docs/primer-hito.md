# Primer hito: análisis local al guardar

## Criterios de aceptación

1. La extensión inicia un proceso Python de larga duración.
2. La comunicación local usa mensajes JSON-RPC delimitados por línea sobre stdin/stdout; los registros se escriben en stderr.
3. Cada solicitud incluye identificador, URI y versión del documento.
4. Una regla inicial acotada produce diagnósticos con identificador, rango y evidencia.
5. Las respuestas correspondientes a versiones anteriores no se publican.
6. Los fallos del proceso se presentan como errores de análisis, nunca como ausencia de riesgos.
7. Los casos de prueba incluyen un positivo, un negativo y una corrección del positivo.

## Límites de esta entrega

Un lenguaje y una regla verificable. Sin inferencia externa, modificación automática de código ni declaración de cobertura completa de seguridad. La selección exacta de la primera regla se documentará junto con sus APIs soportadas.
