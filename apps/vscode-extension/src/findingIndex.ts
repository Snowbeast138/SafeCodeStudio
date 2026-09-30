import * as path from 'node:path';
import { Finding } from './types';

export interface FindingCounts { errors: number; warnings: number }
export interface FindingIndex {
  files: Map<string, FindingCounts>;
  folders: Map<string, FindingCounts>;
}

function increment(map: Map<string, FindingCounts>, key: string, error: boolean): void {
  const counts = map.get(key) || { errors: 0, warnings: 0 };
  if (error) counts.errors += 1;
  else counts.warnings += 1;
  map.set(key, counts);
}

export function buildFindingIndex(findings: Finding[]): FindingIndex {
  const files = new Map<string, FindingCounts>();
  const folders = new Map<string, FindingCounts>();
  for (const finding of findings) {
    const file = path.posix.normalize(finding.path.replaceAll('\\', '/')).replace(/^\.\//, '');
    if (!file || file === '.' || file.startsWith('../') || path.posix.isAbsolute(file)) continue;
    const error = finding.severity === 'high';
    increment(files, file, error);
    for (let directory = path.posix.dirname(file); directory !== '.' && directory !== '/'; directory = path.posix.dirname(directory)) {
      increment(folders, directory, error);
    }
  }
  return { files, folders };
}
