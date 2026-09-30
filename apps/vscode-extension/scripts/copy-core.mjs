import { cp, mkdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';

const extension = resolve(import.meta.dirname, '..');
const source = process.env.SAFECODE_CORE_SOURCE
  ? resolve(process.env.SAFECODE_CORE_SOURCE)
  : resolve(extension, '../../packages/core/src/safecode_core');
const destination = resolve(extension, 'python/safecode_core');
await mkdir(resolve(extension, 'python'), { recursive: true });
await rm(destination, { recursive: true, force: true });
await cp(source, destination, {
  recursive: true,
  filter: path => !path.includes('__pycache__') && !path.endsWith('.pyc'),
});
