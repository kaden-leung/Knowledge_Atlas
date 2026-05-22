#!/usr/bin/env python3
"""Load the POE-EXT substitution-graph seed into substitution_graph.db.

Reads data/poe_ext_substitution_seed.json -- 32 constructs, 39 measures,
and 47 construct-measure links covering POE-EXT-1..8 from the corpus
extraction agenda -- and upserts it into the substitution graph.

Constructs and measures use INSERT OR IGNORE, so pre-existing base rows
(the attention-restoration worked example) are preserved. Links are
replaced per (construct_id, measure_id) pair, so re-running the loader is
idempotent rather than additive.

substitution_graph.db is an operator-local, git-ignored artifact, and
AG's substitution-graph extraction pass later overwrites the
CW-estimated construct_validity / field_acceptance / citation_count
numbers with per-paper extracted values. This loader exists so the
seed -> db step is reproducible whenever the local db is rebuilt.

Usage:
    python3 scripts/load_poe_ext_substitution_seed.py [seed.json] [db]
"""
import json
import sqlite3
import sys

SEED = sys.argv[1] if len(sys.argv) > 1 else 'data/poe_ext_substitution_seed.json'
DB = sys.argv[2] if len(sys.argv) > 2 else 'data/substitution_graph.db'


def enc(value):
    """JSON-encode lists/dicts for storage in TEXT columns; pass scalars."""
    return json.dumps(value) if isinstance(value, (list, dict)) else value


def main():
    with open(SEED) as fh:
        seed = json.load(fh)

    con = sqlite3.connect(DB)
    cur = con.cursor()

    before = {t: cur.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
              for t in ('constructs', 'measures', 'construct_measure_links')}

    for c in seed['constructs']:
        cur.execute(
            'INSERT OR IGNORE INTO constructs '
            '(construct_id, canonical_name, aliases, family_theory_id, '
            ' proliferation_warning) VALUES (?,?,?,?,?)',
            (c['construct_id'], c['canonical_name'], enc(c.get('aliases')),
             c.get('family_theory_id'), enc(c.get('proliferation_warning'))))

    for m in seed['measures']:
        cur.execute(
            'INSERT OR IGNORE INTO measures '
            '(measure_id, short_code, canonical_name, measurement_family, '
            ' vr_tractable, vr_tractability_conditions, psychometric_profile, '
            ' construct_validity_per_paper, administration_time_min, '
            ' hardware_required, principal_pitfall, canonical_references) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (m['measure_id'], m.get('short_code'), m['canonical_name'],
             m.get('measurement_family'), 1 if m.get('vr_tractable') else 0,
             enc(m.get('vr_tractability_conditions')),
             enc(m.get('psychometric_profile')),
             enc(m.get('construct_validity_per_paper')),
             m.get('administration_time_min'), enc(m.get('hardware_required')),
             m.get('principal_pitfall'), enc(m.get('canonical_references'))))

    for lk in seed['construct_measure_links']:
        cur.execute(
            'DELETE FROM construct_measure_links '
            'WHERE construct_id=? AND measure_id=?',
            (lk['construct_id'], lk['measure_id']))
        cur.execute(
            'INSERT INTO construct_measure_links '
            '(construct_id, measure_id, construct_validity, field_acceptance, '
            ' canonical_paper_id, citation_count, severity_average, notes) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (lk['construct_id'], lk['measure_id'], lk.get('construct_validity'),
             lk.get('field_acceptance'), lk.get('canonical_paper_id'),
             lk.get('citation_count'), lk.get('severity_average'),
             lk.get('notes')))

    con.commit()
    after = {t: cur.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
             for t in ('constructs', 'measures', 'construct_measure_links')}
    con.close()

    for t in ('constructs', 'measures', 'construct_measure_links'):
        print('%-24s %3d -> %3d' % (t, before[t], after[t]))


if __name__ == '__main__':
    main()
