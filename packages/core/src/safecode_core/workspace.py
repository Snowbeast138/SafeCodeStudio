"""Versioned, persistent analysis contract for a future editor client."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .directory_graph import DirectoryGraphEngine
from .incremental_graph import IncrementalDirectoryGraphEngine
from .security import RULES, _scan_file, architecture_findings, validate_policy
from .git_baseline import git_baseline_snapshot


def _finding_key(finding):
    start = finding.get('start') or {}
    basis = (finding['rule_id'], finding['path'], start.get('line'),
             start.get('byte_column'), finding['evidence'])
    return sha256(json.dumps(basis, ensure_ascii=False).encode('utf-8')).hexdigest()[:20]


def _graph_delta(previous, current):
    old_nodes = previous.graph.nodes if previous else {}
    new_nodes = current.graph.nodes
    old_edges = {(a, b, k): d for a, b, k, d in previous.graph.edges(keys=True, data=True)} if previous else {}
    new_edges = {(a, b, k): d for a, b, k, d in current.graph.edges(keys=True, data=True)}
    return dict(
        nodes_added=[dict(id=n, **new_nodes[n]) for n in sorted(set(new_nodes) - set(old_nodes))],
        nodes_removed=sorted(set(old_nodes) - set(new_nodes)),
        nodes_updated=[dict(id=n, **new_nodes[n]) for n in sorted(set(new_nodes) & set(old_nodes))
                       if new_nodes[n] != old_nodes[n]],
        edges_added=[dict(source=a, target=b, id=k, **new_edges[a, b, k])
                     for a, b, k in sorted(set(new_edges) - set(old_edges))],
        edges_updated=[dict(source=a, target=b, id=k, **new_edges[a, b, k])
                       for a, b, k in sorted(set(new_edges) & set(old_edges))
                       if new_edges[a, b, k] != old_edges[a, b, k]],
        edges_removed=[dict(source=a, target=b, id=k)
                       for a, b, k in sorted(set(old_edges) - set(new_edges))],
    )


def _reference_delta(previous, current):
    old = {item['id']: item for item in previous.references} if previous else {}
    new = {item['id']: item for item in current.references}
    return dict(added=[new[k] for k in sorted(new.keys() - old.keys())],
                updated=[new[k] for k in sorted(new.keys() & old.keys()) if new[k] != old[k]],
                removed=sorted(old.keys() - new.keys()))


class WorkspaceEngine:
    """Single-worker analysis session. Call update with increasing workspace versions."""

    def __init__(self, root, baseline=None, policy=None, git_baseline_ref=None, **graph_options):
        self.root = Path(root).expanduser().resolve()
        if baseline and git_baseline_ref:
            raise ValueError('Choose either a baseline directory or a Git baseline ref')
        self.workspace_id = sha256(str(self.root).encode('utf-8')).hexdigest()[:16]
        self.graph_engine = IncrementalDirectoryGraphEngine(self.root, include_cst=True, **graph_options)
        self.baseline_info = None
        if git_baseline_ref:
            self.baseline, self.baseline_info = git_baseline_snapshot(self.root, git_baseline_ref, **graph_options)
        elif baseline:
            self.baseline = DirectoryGraphEngine(baseline, **graph_options).analyze()
            self.baseline_info = dict(kind='directory', path=str(Path(baseline).expanduser().resolve()))
        else:
            self.baseline = None
        self.forbidden = None
        if policy:
            if self.baseline is None:
                raise ValueError('A layer policy requires a baseline directory or Git revision')
            config = json.loads(Path(policy).read_text(encoding='utf-8'))
            if not isinstance(config, dict) or 'forbidden' not in config:
                raise ValueError('Policy must contain a forbidden list')
            validate_policy(config['forbidden'])
            self.forbidden = config['forbidden']
        self.last_version = -1
        self.last_snapshot = None
        self.last_findings = {}
        self.rule_cache = {}

    def update(self, request_id, version):
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            raise ValueError('request_id must be a string or integer')
        if isinstance(version, bool) or not isinstance(version, int) or version <= self.last_version:
            raise ValueError('version must be an integer greater than the previous version')
        result = self.graph_engine.analyze()
        snapshot = result.snapshot
        for rel in result.changes['removed']:
            self.rule_cache.pop(rel, None)
        for rel in result.changes['added'] + result.changes['modified']:
            report = snapshot.csts.get('file:' + rel)
            self.rule_cache[rel] = _scan_file(rel, report) if report and report['status'] == 'parsed' else []
        findings = [item for rel in sorted(self.rule_cache) for item in self.rule_cache[rel]]
        if self.baseline:
            findings.extend(architecture_findings(snapshot, self.baseline, self.forbidden))
        findings.sort(key=lambda f: (f['path'], (f['start'] or {}).get('line', 0), f['rule_id']))
        current_findings = {_finding_key(item): item for item in findings}
        coverage = {rule: 'analyzed' if rule.startswith('SEG') or
                    (rule == 'ARQ-01' and self.baseline is not None) or
                    (rule == 'ARQ-02' and self.forbidden is not None) else 'skipped'
                    for rule in RULES}
        issues = snapshot.issues + (self.baseline.issues if self.baseline else [])
        status = 'partial' if issues or 'skipped' in coverage.values() else 'complete_for_supported_scope'
        payload = dict(schema_version=1, request_id=request_id, workspace_id=self.workspace_id,
                       version=version, generated_at=datetime.now(timezone.utc).isoformat(),
                       root=str(self.root), status=status, coverage=coverage, baseline=self.baseline_info,
                       changes=result.changes, graph_delta=_graph_delta(self.last_snapshot, snapshot),
                       reference_delta=_reference_delta(self.last_snapshot, snapshot),
                       findings=findings,
                       findings_delta=dict(added=[current_findings[k] for k in sorted(current_findings.keys() - self.last_findings.keys())],
                                           resolved=[self.last_findings[k] for k in sorted(self.last_findings.keys() - current_findings.keys())]),
                       issues=issues, excluded=snapshot.excluded,
                       metrics=dict(**result.metrics, findings=len(findings),
                                    by_rule=dict(Counter(f['rule_id'] for f in findings))))
        self.last_version = version
        self.last_snapshot = snapshot
        self.last_findings = current_findings
        return payload

    def graph_snapshot(self, directory='.'):
        if self.last_snapshot is None:
            raise ValueError('Analyze the workspace before requesting a graph snapshot')
        report = self.last_snapshot.to_dict(directory)
        report['rebuild'] = 'incremental_cst_and_edges'
        report['csts'] = {}  # source code and full CST stay inside the local engine
        return report
