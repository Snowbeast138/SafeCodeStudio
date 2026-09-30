import { Finding } from './types';

export type Language = 'es' | 'en';
export type LanguageSetting = 'auto' | Language;

export function resolveLanguage(setting: string, editorLanguage: string): Language {
  if (setting === 'es' || setting === 'en') return setting;
  return editorLanguage.toLowerCase().startsWith('es') ? 'es' : 'en';
}

export function tx(language: Language, spanish: string, english: string): string {
  return language === 'es' ? spanish : english;
}

const FINDINGS: Record<string, { title: string; explanation: string }> = {
  'SEG-01': { title: 'SQL query built from external input', explanation: 'External input is used to build a SQL query executed by a supported API. Use bound parameters.' },
  'SEG-02': { title: 'Shell command built from external input', explanation: 'External input is used in a command executed through a shell. Pass arguments separately and avoid shell execution.' },
  'SEG-03': { title: 'Hard-coded credential', explanation: 'A literal is assigned to a credential identifier. Check whether it should come from secure configuration.' },
  'ARQ-01': { title: 'New cycle between modules', explanation: 'An added dependency creates a cycle relative to the baseline version.' },
  'ARQ-02': { title: 'New forbidden dependency between layers', explanation: 'The new import violates the explicit layer policy.' },
};

export function localizeFinding(finding: Finding, language: Language): Finding {
  const translation = FINDINGS[finding.rule_id];
  if (language === 'es' || !translation) return finding;
  return { ...finding, title: translation.title, explanation: translation.explanation,
    evidence: finding.rule_id === 'SEG-03' ? finding.evidence.replace('[valor omitido]', '[value redacted]') : finding.evidence };
}

const GRAPH_PHRASES: [string, string][] = [
  ['ANÁLISIS DE DEPENDENCIAS', 'DEPENDENCY ANALYSIS'],
  ['Relaciones entre archivos', 'File relationships'],
  ['Importador → dependencia · Evidencia del CST · Snapshot estático', 'Importer → dependency · CST evidence · Static snapshot'],
  ['Subgrafo de carpeta', 'Folder subgraph'],
  ['Resumen del análisis', 'Analysis summary'],
  ['Sin aristas locales no significa ausencia de dependencias externas o dinámicas. Los archivos de otros formatos se muestran sin analizar.', 'No local edges does not mean there are no external or dynamic dependencies. Files in other formats are shown without analysis.'],
  ['Mapa de dependencias', 'Dependency map'],
  ['Relaciones de frontera de la carpeta', 'Folder boundary relationships'],
  ['Referencias no resueltas localmente', 'References not resolved locally'],
  ['resueltas', 'resolved'],
  ['Errores y exclusiones del análisis', 'Analysis errors and exclusions'],
  ['Relaciones internas', 'Internal relationships'],
  ['Cruzan carpetas', 'Cross folders'],
  ['fuera de carpeta', 'outside folder'],
  ['Carpeta sin archivos', 'Folder has no files'],
  ['Sin parser', 'No parser'],
  ['nodos CST', 'CST nodes'],
  ['diagnósticos', 'diagnostics'],
  ['Lo importan', 'Imported by'],
  ['Importa a', 'Imports'],
  ['Referencias desde otros archivos hacia este archivo.', 'References from other files to this file.'],
  ['Referencias de este archivo hacia sus dependencias.', 'References from this file to its dependencies.'],
  ['Autorreferencia', 'Self-reference'],
  ['Sin coincidencias para esta búsqueda.', 'No matches for this search.'],
  ['Sin relaciones locales detectadas.', 'No local relationships detected.'],
  ['Sin relaciones de frontera detectadas.', 'No folder boundary relationships detected.'],
  ['Sin referencias pendientes detectadas.', 'No unresolved references detected.'],
  ['Expresión dinámica', 'Dynamic expression'],
  ['Estos archivos dependen del seleccionado.', 'These files depend on the selected file.'],
  ['El seleccionado depende de estos archivos.', 'The selected file depends on these files.'],
  ['Fuera de esta carpeta', 'Outside this folder'],
  ['Sin coincidencias.', 'No matches.'],
  ['Página anterior', 'Previous page'],
  ['Página siguiente', 'Next page'],
  ['Selecciona una carpeta con archivos para explorar sus relaciones.', 'Select a folder with files to explore its relationships.'],
  ['RELACIONES DIRECTAS', 'DIRECT RELATIONSHIPS'],
  ['Cada tarjeta es un archivo. Selecciónala para seguir sus dependencias; la evidencia completa permanece en el detalle.', 'Each card is a file. Select one to follow its dependencies; full evidence remains in the details.'],
  ['Buscar entre las relaciones', 'Search relationships'],
  ['Nombre o ruta del archivo', 'File name or path'],
  ['ARCHIVO SELECCIONADO', 'SELECTED FILE'],
  ['Vista de un salto:', 'One-hop view:'],
  ['archivos entrantes y', 'incoming files and'],
  ['salientes. Las conexiones entre otros archivos no se dibujan aquí.', 'outgoing files. Connections between other files are not drawn here.'],
  ['Explorar ', 'Explore '],
  ['referencia', 'reference'],
  ['línea', 'line'],
  ['archivos', 'files'],
  ['de ${allLinks.length}', 'of ${allLinks.length}'],
  ['Archivo', 'File'],
  ['Archivos', 'Files'],
];

export function localizeGraphHtml(html: string, language: Language): string {
  if (language === 'es') return html;
  const marker = '<script type="application/json" id="data">';
  const start = html.indexOf(marker);
  const end = start < 0 ? -1 : html.indexOf('</script>', start);
  const translate = (part: string) => {
    let out = part;
    for (const [spanish, english] of GRAPH_PHRASES) out = out.replaceAll(spanish, english);
    return out;
  };
  if (start < 0 || end < 0) return translate(html).replace('<html lang="es">', '<html lang="en">');
  return (translate(html.slice(0, start)) + html.slice(start, end + 9) + translate(html.slice(end + 9)))
    .replace('<html lang="es">', '<html lang="en">');
}
