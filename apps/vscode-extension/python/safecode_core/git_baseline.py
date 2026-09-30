"""Read a committed Git tree as a baseline without changing the working tree."""
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from .cst import EXTENSIONS
from .directory_graph import DirectoryGraphEngine


def _git(root, *args):
    try:
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'Git baseline unavailable: {exc}') from exc
    if result.returncode:
        raise ValueError(f'Git baseline error: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout.strip()


def git_baseline_snapshot(root, ref, **graph_options):
    """Return (graph, metadata) for a Git commit visible from ``root``.

    Only supported source contents are copied. Unsupported files become empty
    placeholders so dependency resolution still sees their paths. Symlinks are
    omitted, matching the graph engine's normal directory policy.
    """
    root = Path(root).expanduser().resolve()
    if not isinstance(ref, str) or not ref.strip() or ref.startswith('-') or '\x00' in ref or '\n' in ref:
        raise ValueError('Git baseline ref must be a non-empty branch, tag, or commit')
    top = Path(_git(root, 'rev-parse', '--show-toplevel')).resolve()
    if not root.is_relative_to(top):
        raise ValueError('Workspace root must be inside the Git repository')
    prefix = root.relative_to(top).as_posix()
    prefix = '' if prefix == '.' else prefix + '/'
    commit = _git(top, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}')
    if len(commit) not in (40, 64) or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Git did not return a valid commit identifier')

    with TemporaryDirectory(prefix='safecode-baseline-') as temporary:
        baseline = Path(temporary)
        command = ['git', '-C', str(top), 'archive', '--format=tar', commit]
        if prefix:
            command.extend(['--', prefix.rstrip('/')])
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            raise ValueError(f'Git baseline unavailable: {exc}') from exc
        files = 0
        source_bytes = 0
        try:
            assert process.stdout is not None
            with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    name = member.name.removeprefix('./')
                    if prefix:
                        if not name.startswith(prefix):
                            continue
                        name = name[len(prefix):]
                    relative = PurePosixPath(name)
                    if not name or relative.is_absolute() or '..' in relative.parts or '.' in relative.parts:
                        raise ValueError('Unsafe path in Git baseline archive')
                    files += 1
                    if files > 20_000:
                        raise ValueError('Git baseline exceeds 20,000 files')
                    target = baseline.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if relative.suffix.lower() in EXTENSIONS:
                        handle = archive.extractfile(member)
                        if handle is None:
                            raise ValueError(f'Cannot read Git baseline file: {name}')
                        content = handle.read(1_000_001)
                        source_bytes += len(content)
                        if source_bytes > 50_000_000:
                            raise ValueError('Git baseline source exceeds 50 MB')
                        target.write_bytes(content)
                    else:
                        target.touch()
            process.stdout.close()
            stderr = process.stderr.read().decode('utf-8', 'replace') if process.stderr else ''
            if process.wait(timeout=30):
                raise ValueError(f'Git baseline archive failed: {stderr.strip()}')
        except (OSError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f'Cannot read Git baseline: {exc}') from exc
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        if not files:
            raise ValueError('The selected Git revision contains no files in this workspace folder')
        graph = DirectoryGraphEngine(baseline, **graph_options).analyze()
    return graph, dict(kind='git', ref=ref, commit=commit)
