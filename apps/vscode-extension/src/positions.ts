/** Tree-sitter columns are UTF-8 bytes; VS Code columns are UTF-16 code units. */
export function byteColumnToUtf16(line: string, byteColumn: number): number {
  const raw = Buffer.from(line, 'utf8');
  const bounded = Math.max(0, Math.min(byteColumn, raw.length));
  return raw.subarray(0, bounded).toString('utf8').length;
}
