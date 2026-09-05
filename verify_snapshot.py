"""Verify the published LS3 experiment with Python's standard library, offline."""
from pathlib import Path
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def main():
    manifest = read('publication_manifest.json')
    summary = read('paired_repetition_summary.json')
    index = read('results/branch_index.json')
    keys = [(v['target_task_id'], v['repetition'], v['condition']) for v in index]
    expected = {(f'E1-LS3-T{t}', rep, cond) for t in (4, 5, 6) for rep in 'ABC'
                for cond in ('no_artifact', 'episodic', 'procedural')}
    assert len(keys) == len(set(keys)) == 27 and set(keys) == expected, 'Incomplete or duplicate branch matrix'
    assert summary['n_branch_runs'] == len(summary['runs']) == manifest['branch_count'] == 27
    shared = ROOT / 'artifacts/shared_source'
    eh = hashlib.sha256((shared / 'normalized_source_evidence.json').read_bytes()).hexdigest()
    ph = hashlib.sha256((shared / 'procedural/SKILL.md').read_bytes()).hexdigest()
    assert eh == manifest['shared_episodic_sha256'] and ph == manifest['shared_procedural_sha256'], 'Shared artifact hash mismatch'
    members = read('artifacts/shared_source/membership.json')
    assert len(members) == len({v['mvp_id'] for v in members}) == 9
    assert all(v['episodic_sha256'] == eh and v['procedural_sha256'] == ph for v in members)
    grouped, costs = defaultdict(list), []
    rows = {(v['target_task_id'], v['repetition'], v['condition']): v for v in summary['runs']}
    assert len(rows) == 27
    for entry in index:
        key = (entry['target_task_id'], entry['repetition'], entry['condition'])
        row = rows[key]
        raw = read(entry['result'])
        trial = read(entry['trial_status'])
        assert raw['normalized_score'] == row['normalized_score']
        assert raw['condition'] == entry['condition']
        assert raw['agent_completed_without_exception'] is True
        assert trial['exception_info'] is None
        assert trial['agent']['model_name'] == 'claude-sonnet-5'
        assert not row['construct_results']['unmatched_failed_tests']
        grouped[(entry['target_task_id'], entry['condition'])].append(raw['normalized_score'])
        costs.append(row['total_cost_usd_estimate'])
    for aggregate in summary['aggregates']:
        scores = grouped[(aggregate['target_task_id'], aggregate['condition'])]
        assert len(scores) == aggregate['n'] == 3
        assert math.isclose(statistics.fmean(scores), aggregate['mean'], abs_tol=1e-12)
        assert math.isclose(statistics.stdev(scores), aggregate['sample_sd'], abs_tol=1e-12)
    assert math.isclose(sum(costs), summary['integrity']['branch_cost_usd_estimate'], abs_tol=1e-9)
    checksums = read('snapshot_checksums.json')
    for relative, expected_sha in checksums.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected_sha, f'File changed: {relative}'
    print(f'PASS: 27 branches, 9 paired groups, shared input/skill hashes, aggregate means/SD, costs and {len(checksums)} evidence-file checksums.')
    print('No API calls, credentials, Docker or third-party Python packages were used.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
