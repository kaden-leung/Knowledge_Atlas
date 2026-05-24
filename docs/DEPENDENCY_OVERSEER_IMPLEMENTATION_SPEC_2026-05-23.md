# Dependency Overseer Implementation Spec

Date: 2026-05-23
Status: Phase 1 implementation contract
Depends on:
- `docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` (design contract; B1–B12, P1–P28, R1–R10, OR1–OR10)
- `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md` (companion contract; Stage 1 deterministic builder)
- `docs/DEPENDENCY_OVERSEER_EXPERT_PANEL_BRIEF_2026-05-23.md` (review brief)
- `docs/HANDOFF_DEPENDENCY_OVERSEER_2026-05-23.md` (handoff)

This document translates the synthesis from design contract into engineering contract. It specifies file paths, SQL, vocabulary file shapes, Python module/class skeletons, the test plan, and acceptance criteria. It does not contain implementation code; it specifies enough that the implementation is unambiguous.

## 1. Scope

This spec covers **Phase 1 only**. Per P28 of the synthesis, Phase 1 lands 17 active tables and 5 scaffold-only tables; the Phase 1 builder writes rows only to the active tables. Phase 2 (Article Finder bridge), Phase 3 (LLM enrichment governance), and Phase 4 (topics / DYK / search / reports) are out of scope here and get their own specs at the start of each phase.

In scope for Phase 1:

- DB migration `v1` creating all 22 tables and indices.
- Four JSON vocabulary files in `schemas/`.
- Seeding `vocabulary_registry` from PsychoPy and a small set of related canonical libraries.
- Deterministic normalization rule v1 for semantic hashing.
- The article-epistemic Stage 1 builder per the companion contract.
- A single-worker rebuild queue with heartbeat-based lease and fencing-token-protected writes.
- The strict data verifier and the rendered-page verifier.
- The repair / completion loop.
- The Phase 1 test plan.
- A round-trip proof on PNU change → article-epistemic invalidation → rebuild → verifier pass.

Out of scope for Phase 1:

- LLM invocations of any kind (the LLM governance tables land empty as scaffold per P28).
- Article Finder peer-DB sync (the `cross_db_sync_events` table lands empty as scaffold).
- `content_equivalence_checks` semantic adjudication (Phase 3).
- Backpressure logic on the rebuild queue (Phase 4).
- Postgres migration (Phase 4 candidate).

## 2. Repository Layout

The following files are created or extended in the `Knowledge_Atlas` repo:

```
schemas/
    status_vocabularies.json              # NEW — closed enums (P26)
    component_types.json                  # NEW — component types and field policies
    absence_reasons.json                  # NEW — controlled empty-content reasons
    artefact_kinds.json                   # NEW — Phase 1 registered kinds
    psychopy_seed.json                    # NEW — open-vocab canonical seeds

migrations/
    overseer_v1__initial.sql              # NEW — full Phase 1 DDL

src/overseer/
    __init__.py                           # NEW
    db.py                                 # NEW — sqlite connection, WAL pragma
    artefact_registry.py                  # NEW
    dependency_edges.py                   # NEW
    support_sets.py                       # NEW
    content_hashes.py                     # NEW — raw_hash + semantic_hash
    normalization.py                      # NEW — rule v1
    rebuild_queue.py                      # NEW — claim/heartbeat/release
    watchdog.py                           # NEW — reclaim expired leases
    build_runs.py                         # NEW
    vocabulary_registry.py                # NEW
    kinds_registry.py                     # NEW
    pipeline_registry.py                  # NEW
    completion_queue.py                   # NEW
    repair_loop.py                        # NEW
    verifier_data.py                      # NEW — strict data verifier
    verifier_render.py                    # NEW — strict rendered verifier
    last_mile_checks.py                   # NEW — production probes

src/builders/
    article_epistemic_builder.py          # NEW — Stage 1 builder

scripts/
    apply_overseer_migration_v1.py        # NEW — runs the SQL migration
    seed_vocabulary_registry.py           # NEW — loads PsychoPy + related
    verify_dependency_overseer_contract.py        # NEW — wraps verifier_data
    verify_dependency_overseer_render_contract.py # NEW — wraps verifier_render
    rebuild_queue_worker.py               # NEW — long-running worker
    rebuild_queue_watchdog.py             # NEW — long-running watchdog

tests/
    test_overseer_schema.py               # NEW
    test_overseer_artefact_registry.py    # NEW
    test_overseer_dependency_edges.py     # NEW
    test_overseer_support_sets.py         # NEW
    test_overseer_content_hashes.py       # NEW
    test_overseer_normalization.py        # NEW
    test_overseer_vocabulary_registry.py  # NEW
    test_overseer_rebuild_queue.py        # NEW
    test_overseer_watchdog.py             # NEW
    test_overseer_invalidation.py         # NEW
    test_overseer_cascade_bound.py        # NEW
    test_overseer_completion_queue.py     # NEW
    test_overseer_data_verifier.py        # NEW
    test_overseer_repair_loop.py          # NEW
    test_overseer_release_gate.py         # NEW
    test_overseer_render_contract.py      # NEW
    test_article_epistemic_builder.py     # NEW
```

The lifecycle DB file is the existing repo DB. The migration extends it; it does not create a new DB.

## 3. DB Migration v1

`migrations/overseer_v1__initial.sql` runs in one transaction. The SQL is grouped by synthesis subsection.

### 3.1 PRAGMAs

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
```

### 3.2 Core overseer tables (active)

```sql
CREATE TABLE artefact_registry (
    artefact_id              TEXT    PRIMARY KEY,
    kind                     TEXT    NOT NULL,
    entity_type              TEXT    NOT NULL,
    entity_id                TEXT    NOT NULL,
    field_path               TEXT,
    schema_version           TEXT    NOT NULL,
    latest_build_run_id      TEXT,
    raw_hash                 TEXT,
    semantic_hash            TEXT,
    current_fencing_token    INTEGER NOT NULL DEFAULT 0,
    freshness_status         TEXT    CHECK(freshness_status IN ('fresh','stale','unknown','building')),
    created_at               TEXT    NOT NULL,
    tombstoned_at            TEXT,
    active                   INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX idx_artefact_active_uniq
    ON artefact_registry(entity_type, entity_id, field_path, schema_version)
    WHERE active = 1;
CREATE INDEX idx_artefact_kind ON artefact_registry(kind, active);
CREATE INDEX idx_artefact_freshness ON artefact_registry(freshness_status, kind);

CREATE TABLE dependency_edges (
    parent_artefact_id   TEXT    NOT NULL,
    child_artefact_id    TEXT    NOT NULL,
    edge_kind            TEXT    NOT NULL CHECK(edge_kind IN ('supports','derived_from','depends_on','grounds')),
    edge_hash            TEXT    NOT NULL,
    created_at           TEXT    NOT NULL,
    tombstoned_at        TEXT,
    PRIMARY KEY (parent_artefact_id, child_artefact_id, edge_kind),
    FOREIGN KEY (parent_artefact_id) REFERENCES artefact_registry(artefact_id),
    FOREIGN KEY (child_artefact_id) REFERENCES artefact_registry(artefact_id)
);
CREATE INDEX idx_edges_child ON dependency_edges(child_artefact_id, edge_kind);

CREATE TABLE content_hashes (
    artefact_id                  TEXT    NOT NULL,
    build_run_id                 TEXT    NOT NULL,
    raw_hash                     TEXT    NOT NULL,
    semantic_hash                TEXT    NOT NULL,
    normalization_rule_version   TEXT    NOT NULL,
    input_fingerprint            TEXT    NOT NULL,
    hashed_at                    TEXT    NOT NULL,
    PRIMARY KEY (artefact_id, build_run_id),
    FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id)
);
CREATE INDEX idx_content_hashes_semantic ON content_hashes(artefact_id, semantic_hash);

CREATE TABLE support_sets (
    support_set_id     TEXT PRIMARY KEY,
    support_set_hash   TEXT NOT NULL,
    members_json       TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TABLE support_set_members (
    support_set_id           TEXT NOT NULL,
    member_artefact_id       TEXT NOT NULL,
    member_hash_at_capture   TEXT NOT NULL,
    PRIMARY KEY (support_set_id, member_artefact_id),
    FOREIGN KEY (support_set_id) REFERENCES support_sets(support_set_id),
    FOREIGN KEY (member_artefact_id) REFERENCES artefact_registry(artefact_id)
);
CREATE INDEX idx_support_member_lookup ON support_set_members(member_artefact_id);

CREATE TABLE build_runs (
    build_run_id          TEXT PRIMARY KEY,
    builder_name          TEXT NOT NULL,
    builder_version       TEXT NOT NULL,
    started_at            TEXT NOT NULL,
    finished_at           TEXT,
    status                TEXT NOT NULL CHECK(status IN ('running','verified','failed','aborted','rehash')),
    input_snapshot_hash   TEXT,
    record_count          INTEGER,
    success_count         INTEGER,
    failure_count         INTEGER,
    report_json           TEXT
);
```

### 3.3 Queue and worker tables (active)

```sql
CREATE TABLE rebuild_queue (
    queue_id                    TEXT    PRIMARY KEY,
    artefact_id                 TEXT    NOT NULL,
    reason                      TEXT,
    severity                    TEXT    NOT NULL CHECK(severity IN ('low','medium','high','blocking')),
    first_seen_at               TEXT    NOT NULL,
    last_seen_at                TEXT    NOT NULL,
    attempt_count               INTEGER NOT NULL DEFAULT 0,
    state                       TEXT    NOT NULL CHECK(state IN ('queued','claimed','building','done','failed','quarantine')),
    lease_owner                 TEXT,
    fencing_token               INTEGER NOT NULL DEFAULT 0,
    claimed_at                  TEXT,
    input_fingerprint_at_claim  TEXT,
    last_error                  TEXT,
    FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id)
);
CREATE INDEX idx_queue_state ON rebuild_queue(state, severity, first_seen_at);
CREATE INDEX idx_queue_lease ON rebuild_queue(lease_owner) WHERE state IN ('claimed','building');

CREATE TABLE worker_heartbeats (
    worker_id                          TEXT    PRIMARY KEY,
    last_heartbeat_at                  TEXT    NOT NULL,
    current_claim                      TEXT,
    heartbeat_interval_seconds         INTEGER NOT NULL,
    heartbeat_timeout_seconds          INTEGER NOT NULL,
    progress_marker                    TEXT,
    progress_marker_unchanged_since    TEXT
);
```

### 3.4 Registry and pipeline tables (active)

```sql
CREATE TABLE artefact_kinds (
    kind_name             TEXT    PRIMARY KEY,
    owner_pipeline        TEXT    NOT NULL,
    support_rule_module   TEXT    NOT NULL,
    schema_version        TEXT    NOT NULL,
    active                INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT    NOT NULL
);

CREATE TABLE pipeline_registry (
    pipeline_name             TEXT PRIMARY KEY,
    version                   TEXT NOT NULL,
    declared_outputs_json     TEXT NOT NULL,
    declared_inputs_json      TEXT NOT NULL,
    last_seen_at              TEXT
);

CREATE TABLE vocabulary_registry (
    value_id                       TEXT PRIMARY KEY,
    kind                           TEXT NOT NULL,
    value                          TEXT NOT NULL,
    canonical_value                TEXT,
    first_seen_in_paper            TEXT,
    first_observed_at              TEXT NOT NULL,
    first_observed_build_run_id    TEXT,
    review_status                  TEXT NOT NULL CHECK(review_status IN ('candidate','canonical','synonym','rejected')),
    canonicalization_source        TEXT,
    seeded_from                    TEXT,
    UNIQUE(kind, value)
);
CREATE INDEX idx_vocab_kind_status ON vocabulary_registry(kind, review_status);
```

### 3.5 Epistemic detail tables (active, per companion contract Phase 1)

```sql
CREATE TABLE claims (
    claim_id                  TEXT PRIMARY KEY,
    paper_id                  TEXT NOT NULL,
    canonical_claim_text      TEXT NOT NULL,
    canonicalizer_version     TEXT NOT NULL,
    original_text             TEXT,
    claim_scope               TEXT,
    claim_type                TEXT,
    claim_polarity            TEXT,
    assertion_status          TEXT,
    epistemic_status          TEXT,
    claim_origin              TEXT NOT NULL CHECK(claim_origin IN (
        'structured_core_finding','top_claims_row','article_level_main_conclusion',
        'science_summary_core_finding','not_extracted'
    )),
    superseded_by             TEXT,
    created_at                TEXT NOT NULL,
    tombstoned_at             TEXT
);
CREATE INDEX idx_claims_paper ON claims(paper_id);

CREATE TABLE defeaters (
    defeater_id       TEXT PRIMARY KEY,
    claim_id          TEXT NOT NULL,
    target_kind       TEXT NOT NULL CHECK(target_kind IN (
        'claim','warrant','method','measurement','interpretation',
        'generalizability','mechanism','application'
    )),
    content_json      TEXT NOT NULL,
    support_set_id    TEXT,
    created_at        TEXT NOT NULL,
    tombstoned_at     TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
    FOREIGN KEY (support_set_id) REFERENCES support_sets(support_set_id)
);

CREATE TABLE belief_network_links (
    record_id            TEXT NOT NULL,
    claim_id             TEXT NOT NULL,
    pnu_id               TEXT NOT NULL,
    pnu_version_hash     TEXT NOT NULL,
    edge_kind            TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    tombstoned_at        TEXT,
    PRIMARY KEY (record_id, claim_id, pnu_id, edge_kind)
);

CREATE TABLE answer_shape_decisions (
    record_id          TEXT NOT NULL,
    shape              TEXT NOT NULL CHECK(shape IN (
        'toulmin','field_map','comparison','mechanism','review_synthesis','mixed','unknown'
    )),
    rule_id            TEXT NOT NULL,
    rule_version       TEXT NOT NULL,
    rule_trace_json    TEXT,
    created_at         TEXT NOT NULL,
    superseded_at      TEXT,
    PRIMARY KEY (record_id, created_at)
);
```

### 3.6 Completion queue (active) and last-mile (active)

```sql
CREATE TABLE completion_queue (
    queue_id          TEXT PRIMARY KEY,
    artefact_id       TEXT,
    paper_id          TEXT,
    component_type    TEXT,
    reason            TEXT NOT NULL,
    severity          TEXT NOT NULL CHECK(severity IN ('low','medium','high','blocking')),
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_action       TEXT,
    status            TEXT NOT NULL CHECK(status IN ('open','in_review','resolved','waived')),
    assigned_to       TEXT,
    resolved_at       TEXT
);
CREATE INDEX idx_completion_open ON completion_queue(status, severity, first_seen_at)
    WHERE status IN ('open','in_review');

CREATE TABLE last_mile_production_checks (
    check_id          TEXT PRIMARY KEY,
    artefact_id       TEXT NOT NULL,
    check_kind        TEXT NOT NULL CHECK(check_kind IN (
        'http_200','asset_200','no_console_error','payload_hash_equal',
        'mobile_layout','provenance_visible'
    )),
    status            TEXT NOT NULL CHECK(status IN ('pass','fail','skipped')),
    evidence_json     TEXT,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id)
);
```

### 3.7 Scaffold-only tables (no rows in Phase 1)

```sql
CREATE TABLE cross_db_sync_events (
    event_id                   TEXT PRIMARY KEY,
    event_kind                 TEXT NOT NULL CHECK(event_kind IN (
        'accept_candidate','registry_snapshot','tombstone_paper','reconcile_paper'
    )),
    lifecycle_payload_hash     TEXT,
    article_finder_payload_hash TEXT,
    status                     TEXT NOT NULL CHECK(status IN ('pending','matched','unresolved','reconciled')),
    created_at                 TEXT NOT NULL,
    resolved_at                TEXT
);

CREATE TABLE llm_invocations (
    invocation_id          TEXT PRIMARY KEY,
    artefact_id            TEXT NOT NULL,
    model_name             TEXT NOT NULL,
    prompt_template_id     TEXT NOT NULL,
    prompt_template_hash   TEXT NOT NULL,
    source_packet_id       TEXT NOT NULL,
    source_packet_hash     TEXT NOT NULL,
    input_hash             TEXT NOT NULL,
    output_hash            TEXT NOT NULL,
    grounding_verdict      TEXT CHECK(grounding_verdict IN (
        'pass','field_pinned_failure','semantic_failure','not_run'
    )),
    reviewer_id            TEXT,
    review_decision        TEXT CHECK(review_decision IN (
        'machine_approved','human_approved','rejected','pending'
    )),
    worker_surface         TEXT NOT NULL CHECK(worker_surface IN (
        'antigravity_subscription','codex_cli_subscription',
        'claude_cli_subscription','google_ai_api'
    )),
    created_at             TEXT NOT NULL,
    FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id)
);

CREATE TABLE prompt_templates (
    prompt_template_id           TEXT PRIMARY KEY,
    prompt_version               TEXT NOT NULL,
    prompt_template_hash         TEXT NOT NULL,
    allowed_field_policies_json  TEXT NOT NULL,
    created_at                   TEXT NOT NULL,
    active                       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE source_packets (
    source_packet_id      TEXT PRIMARY KEY,
    members_json          TEXT NOT NULL,
    source_packet_hash    TEXT NOT NULL,
    created_at            TEXT NOT NULL
);

CREATE TABLE content_equivalence_checks (
    check_id                       TEXT PRIMARY KEY,
    artefact_id                    TEXT NOT NULL,
    prior_raw_hash                 TEXT NOT NULL,
    new_raw_hash                   TEXT NOT NULL,
    prior_semantic_hash            TEXT NOT NULL,
    new_semantic_hash              TEXT NOT NULL,
    equivalence_verdict            TEXT NOT NULL CHECK(equivalence_verdict IN (
        'semantic_equivalent','semantic_distinct','unresolved'
    )),
    llm_invocation_id              TEXT,
    normalization_rule_version     TEXT NOT NULL,
    created_at                     TEXT NOT NULL,
    FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id),
    FOREIGN KEY (llm_invocation_id) REFERENCES llm_invocations(invocation_id)
);
```

## 4. JSON Vocabulary Files

All four files are committed to git before the migration runs. Their `version` field is bumped only via a controlled migration; the verifier rejects drift.

### 4.1 `schemas/status_vocabularies.json`

Closed enums only, per P26.

```json
{
  "version": "v1",
  "freshness_status": ["fresh", "stale", "unknown", "building"],
  "extraction_status": ["absent", "minimal", "partial", "complete", "failed"],
  "enrichment_status": ["none", "deferred", "draft", "machine_checked", "human_approved", "rejected"],
  "review_status_record": ["not_required", "unreviewed", "machine_verified", "human_review_required", "human_approved", "human_rejected"],
  "render_status": ["renderable", "show_with_warning", "hidden", "block_article"],
  "component_status": ["present", "not_extracted", "not_applicable", "source_missing", "extraction_failed", "stale", "blocked", "queued", "withheld_low_confidence"],
  "source_mode": ["extracted", "deterministic_derived", "llm_generated", "human_entered", "missing"],
  "field_policy": ["extracted_only", "deterministic_only", "llm_enrichable", "human_only"],
  "severity": ["low", "medium", "high", "blocking"],
  "queue_state": ["queued", "claimed", "building", "done", "failed", "quarantine"],
  "edge_kind": ["supports", "derived_from", "depends_on", "grounds"],
  "defeater_target_kind": ["claim", "warrant", "method", "measurement", "interpretation", "generalizability", "mechanism", "application"],
  "claim_origin": ["structured_core_finding", "top_claims_row", "article_level_main_conclusion", "science_summary_core_finding", "not_extracted"],
  "answer_shape": ["toulmin", "field_map", "comparison", "mechanism", "review_synthesis", "mixed", "unknown"],
  "worker_surface": ["antigravity_subscription", "codex_cli_subscription", "claude_cli_subscription", "google_ai_api"],
  "grounding_verdict": ["pass", "field_pinned_failure", "semantic_failure", "not_run"],
  "review_decision": ["machine_approved", "human_approved", "rejected", "pending"],
  "vocabulary_review_status": ["candidate", "canonical", "synonym", "rejected"],
  "event_kind": ["accept_candidate", "registry_snapshot", "tombstone_paper", "reconcile_paper"],
  "sync_status": ["pending", "matched", "unresolved", "reconciled"],
  "check_kind": ["http_200", "asset_200", "no_console_error", "payload_hash_equal", "mobile_layout", "provenance_visible"],
  "check_status": ["pass", "fail", "skipped"],
  "equivalence_verdict": ["semantic_equivalent", "semantic_distinct", "unresolved"]
}
```

### 4.2 `schemas/component_types.json`

Each Phase 1 component type declares allowed statuses, default render policy, default field policy, and the per-field normalization hints used by rule v1.

```json
{
  "version": "v1",
  "component_types": {
    "primary_claim": {
      "allowed_statuses": ["present", "not_extracted", "source_missing", "stale", "blocked"],
      "default_render_policy": "renderable",
      "default_field_policy": "extracted_only",
      "normalization_hints": {
        "canonical_claim_text": {"whitespace_collapsible": true, "case_insensitive": false},
        "claim_scope": {"case_insensitive": true}
      }
    },
    "claim_rows": {
      "allowed_statuses": ["present", "not_extracted", "stale"],
      "default_render_policy": "renderable",
      "default_field_policy": "extracted_only"
    },
    "evidence_strength": {
      "allowed_statuses": ["present", "not_applicable", "withheld_low_confidence", "stale"],
      "default_render_policy": "renderable",
      "default_field_policy": "deterministic_only"
    },
    "defeaters": {
      "allowed_statuses": ["present", "not_extracted", "stale", "blocked"],
      "default_render_policy": "show_with_warning",
      "default_field_policy": "extracted_only"
    },
    "belief_network_context": {
      "allowed_statuses": ["present", "not_applicable", "stale", "source_missing"],
      "default_render_policy": "renderable",
      "default_field_policy": "deterministic_only"
    },
    "answer_shape_status": {
      "allowed_statuses": ["present", "stale"],
      "default_render_policy": "renderable",
      "default_field_policy": "deterministic_only"
    },
    "provenance_summary": {
      "allowed_statuses": ["present"],
      "default_render_policy": "renderable",
      "default_field_policy": "deterministic_only"
    }
  }
}
```

### 4.3 `schemas/absence_reasons.json`

```json
{
  "version": "v1",
  "absence_reasons": [
    "no_source_content",
    "not_yet_extracted",
    "attack_count_without_mapped_rows",
    "no_defeater_extracted",
    "no_defeater_exists",
    "no_pnu_support_available",
    "rule_did_not_fire",
    "phase_2_deferred",
    "phase_3_deferred",
    "withheld_low_confidence"
  ]
}
```

### 4.4 `schemas/artefact_kinds.json`

Phase 1 registered kinds.

```json
{
  "version": "v1",
  "kinds": [
    {
      "kind_name": "pnu_row",
      "owner_pipeline": "pnu_builder",
      "support_rule_module": "src.overseer.support_rules.pnu_row",
      "schema_version": "pnu_row.v1",
      "phase_active": 1
    },
    {
      "kind_name": "article_epistemic_record",
      "owner_pipeline": "article_epistemic_builder",
      "support_rule_module": "src.overseer.support_rules.article_epistemic_record",
      "schema_version": "article_epistemic_layer.v1",
      "phase_active": 1
    },
    {
      "kind_name": "article_detail_json",
      "owner_pipeline": "article_detail_payload_builder",
      "support_rule_module": "src.overseer.support_rules.article_detail_json",
      "schema_version": "article_detail.v1",
      "phase_active": 1
    }
  ]
}
```

## 5. Vocabulary Seeding

`schemas/psychopy_seed.json` carries the initial canonical entries. The shape:

```json
{
  "version": "v1",
  "seeds": [
    {"kind": "instrument_name", "value": "Stroop Task", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "Digit Span Task", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "N-Back Task", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "Posner Cueing Task", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "Trier Social Stress Test", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "International Affective Picture System", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "Self-Assessment Manikin", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "PANAS", "seeded_from": "psychopy.v2024.2"},
    {"kind": "instrument_name", "value": "STAI", "seeded_from": "psychopy.v2024.2"},
    {"kind": "measure_name", "value": "salivary cortisol", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "measure_name", "value": "heart rate variability", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "measure_name", "value": "skin conductance response", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "measure_name", "value": "EEG alpha power", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "measure_name", "value": "reaction time", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "measure_name", "value": "accuracy", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "construct_label", "value": "stress", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "construct_label", "value": "anxiety", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "construct_label", "value": "attention", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "construct_label", "value": "memory", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "construct_label", "value": "affect", "seeded_from": "cnfa_canonical.v1"},
    {"kind": "abstract_source_label", "value": "crossref", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "openalex", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "publisher_metadata", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "pdf_extracted", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "llm_summarized_from_pdf", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "manual", "seeded_from": "article_finder_canonical.v1"},
    {"kind": "abstract_source_label", "value": "missing", "seeded_from": "article_finder_canonical.v1"}
  ]
}
```

The seed list above is a starter, not exhaustive. The implementation team extends it before the Phase 1 ship gate. Each seed row is inserted into `vocabulary_registry` with `review_status='canonical'`, `first_observed_at=now()`, and `first_seen_in_paper=NULL`.

`scripts/seed_vocabulary_registry.py` reads the JSON file and performs an idempotent insert (insert-or-skip on `UNIQUE(kind, value)`).

## 6. Normalization Rule v1

`src/overseer/normalization.py` implements rule v1 as a pure function.

```python
def normalize_for_semantic_hash(content: dict, component_type: str, rule_version: str = "v1") -> bytes:
    """
    Deterministic normalization for semantic hashing.

    Rule v1 algorithm:
      1. Look up component_type's normalization_hints in schemas/component_types.json.
      2. Walk the content tree depth-first:
         a. For dict nodes: sort keys lexicographically.
         b. For list nodes whose path is declared 'order_insensitive' in the hints,
            sort the list using a deterministic key function (canonical JSON of each
            element).
         c. For string leaves whose path is declared 'whitespace_collapsible':
            - strip leading/trailing whitespace
            - collapse internal whitespace runs to a single space
         d. For string leaves whose path is declared 'case_insensitive':
            - lowercase
         e. For paths declared 'cosmetic_only' (timestamps, build run IDs, formatting
            metadata): drop the key from the output.
      3. Serialize the normalized tree as canonical JSON: UTF-8, sorted keys, compact
         separators (',', ':'), no extra whitespace.
      4. Return the resulting byte string.

    The caller computes SHA-256 over the returned bytes; that is semantic_hash.

    Raw hash is computed the same way on the input content WITHOUT step 2, only with
    canonical JSON serialization in step 3. raw_hash captures byte-level identity;
    semantic_hash captures meaning-level identity under rule v1.
    """
```

Invariants enforced by rule v1:

- The same input always produces the same output bytes (deterministic).
- Whitespace, key ordering, and (where declared) order/case differences do not change `semantic_hash`.
- Any field not explicitly marked `cosmetic_only` is preserved in the normalized form.
- `normalization_rule_version="v1"` is recorded on every `content_hashes` row.

## 7. Hash Computation

```python
import hashlib
import json

def compute_raw_hash(content: dict) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()

def compute_semantic_hash(content: dict, component_type: str, rule_version: str = "v1") -> str:
    normalized = normalize_for_semantic_hash(content, component_type, rule_version)
    return "sha256:" + hashlib.sha256(normalized).hexdigest()

def compute_input_fingerprint(support_set: list[tuple[str, str]]) -> str:
    """
    support_set is a list of (member_artefact_id, member_hash_at_capture).
    The fingerprint is the SHA-256 of the canonical JSON of the sorted list.
    """
    canonical = json.dumps(sorted(support_set), separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
```

## 8. Builder Skeleton

`src/builders/article_epistemic_builder.py`:

```python
class ArticleEpistemicBuilder:
    """Stage 1 deterministic builder per the companion contract."""

    BUILDER_NAME = "article_epistemic_builder"
    BUILDER_VERSION = "v1"
    SCHEMA_VERSION = "article_epistemic_layer.v1"

    def __init__(self, db, kinds_registry, vocab_registry, normalization_rule_version="v1"):
        ...

    def build_one(self, paper_id: str, build_run_id: str, fencing_token: int) -> BuildResult:
        """
        Build the article_epistemic_record for one paper.

        Steps:
          1. Capture input snapshot: read existing article_details, top_claims,
             argumentation, evidence_profile, abstract, PNU rows if present.
          2. Build the support set (artefact_ids of every input row read).
          3. Compute input_fingerprint from the support set.
          4. Select primary_claim via the rule cascade (companion contract §8);
             record which rule fired in claim_origin.
          5. Build claim_rows.
          6. Compute evidence_strength bound to each claim.
          7. Enumerate defeaters; if attack_count > 0 with no mapped rows, emit
             absence_reason=attack_count_without_mapped_rows.
          8. Build belief_network_links if PNU support is available; else emit
             absence_reason=no_pnu_support_available.
          9. Assign answer_shape via the rule cascade; if no rule fires with
             confidence, assign 'unknown' with the rule trace recorded.
         10. Compose the public payload.
         11. Compute raw_hash and semantic_hash.
         12. Write atomically:
             - upsert artefact_registry with WHERE current_fencing_token = :fencing_token
             - insert content_hashes row
             - insert support_set + support_set_members
             - upsert claims, defeaters, belief_network_links, answer_shape_decisions
             - update freshness_status='fresh'
            All under one DB transaction.
         13. Return BuildResult(record_id, payload_hash, status='verified').

        Raises:
          FencingTokenMismatchError if any write fails the fencing_token check.
          BuildAbortedError if the input fingerprint changed between capture and write.
        """

    def _select_primary_claim(self, paper_id: str) -> tuple[ClaimRow, str]:
        """Returns (claim, claim_origin). Implements the §8 rule cascade."""

    def _enumerate_defeaters(self, paper_id: str, claims: list) -> list[Defeater]:
        """Each defeater row must have a non-null target_kind."""

    def _assign_answer_shape(self, paper_id: str, claims: list) -> AnswerShapeDecision:
        """If no rule fires, returns AnswerShapeDecision(shape='unknown', rule_trace=...)."""

    def _capture_support_set(self, sources: list[ArtefactRef]) -> SupportSet:
        """Hashes each source member at capture time."""

    def _write_atomic(self, record, fencing_token: int) -> None:
        """Single transaction. Fencing-token-protected. Raises on conflict."""
```

Acceptance for the builder:

- Builds an `article_epistemic_record` for a paper with the full input set in under five seconds (on the existing repo DB).
- Honors every rule in the companion contract §8 deterministically.
- Idempotent: rerunning with identical inputs and identical `normalization_rule_version` produces identical `raw_hash` and `semantic_hash`.
- Refuses to write if the fencing token does not match the artefact's current token.

## 9. Rebuild Queue Worker

`src/overseer/rebuild_queue.py`:

```python
class RebuildQueueWorker:
    HEARTBEAT_INTERVAL_SECONDS = 30
    HEARTBEAT_TIMEOUT_SECONDS = 300  # 5 minutes; 10x interval

    def __init__(self, db, worker_id: str, builder: Builder):
        ...

    def run_forever(self) -> None:
        """Main loop. Claim → heartbeat-while-building → complete/fail. Exits on signal."""

    def claim_one(self) -> Claim | None:
        """
        Atomically:
          BEGIN
            SELECT queue_id, artefact_id FROM rebuild_queue
              WHERE state='queued' AND severity ORDER BY first_seen_at
              LIMIT 1;
            UPDATE artefact_registry
              SET current_fencing_token = current_fencing_token + 1
              WHERE artefact_id = :artefact_id;
            UPDATE rebuild_queue
              SET state='claimed', lease_owner=:worker_id, claimed_at=now(),
                  fencing_token=(new current_fencing_token from above),
                  input_fingerprint_at_claim=:fingerprint_now
              WHERE queue_id=:queue_id AND state='queued';
            UPSERT worker_heartbeats SET last_heartbeat_at=now(), current_claim=:queue_id;
          COMMIT;
        Returns Claim(queue_id, artefact_id, fencing_token) or None if queue empty.
        """

    def heartbeat(self, progress_marker: str | None = None) -> None:
        """Updates worker_heartbeats.last_heartbeat_at; optionally progress_marker.
           If progress_marker is provided and equals the previous marker, leaves
           progress_marker_unchanged_since alone (do not reset); else updates it
           to now(). Phase 2 reads this column for soft-stuck detection.
        """

    def complete(self, claim: Claim, result: BuildResult) -> None:
        """
        Under the claim's fencing_token:
          UPDATE rebuild_queue SET state='done' WHERE queue_id=:claim.queue_id;
          UPDATE worker_heartbeats SET current_claim=NULL WHERE worker_id=:worker_id;
        Builder's writes to artefact_registry happened earlier under the same fencing_token.
        """

    def fail(self, claim: Claim, error: str) -> None:
        """
        UPDATE rebuild_queue SET
          state = CASE WHEN attempt_count + 1 >= 5 THEN 'quarantine' ELSE 'queued' END,
          attempt_count = attempt_count + 1,
          last_error = :error,
          lease_owner = NULL,
          claimed_at = NULL
        WHERE queue_id=:claim.queue_id;
        """
```

`src/overseer/watchdog.py`:

```python
class RebuildWatchdog:
    """Periodic reclaim of expired-heartbeat claims."""

    TICK_INTERVAL_SECONDS = 60

    def tick(self) -> WatchdogReport:
        """
        For each worker_heartbeats row where now() - last_heartbeat_at > heartbeat_timeout_seconds:
          - Read current_claim if set.
          - For that queue row:
            - Increment artefact_registry.current_fencing_token (invalidates any pending
              writes the dead worker might still try to commit).
            - Reset state='queued', lease_owner=NULL, claimed_at=NULL.
            - Increment attempt_count; if >= 5, set state='quarantine' and emit a
              completion_queue row with severity='high'.
          - Delete the worker_heartbeats row (the worker is presumed gone).
        Returns a structured report listing reclaimed claims.
        """
```

## 10. Verifier Skeleton

`src/overseer/verifier_data.py` exposes one entrypoint that runs every check listed in synthesis §4 and returns a structured report. Each check is one function.

```python
@dataclass
class CheckResult:
    name: str
    passed: bool
    failures: list[dict]  # each failure has artefact_id / queue_id / paper_id / message

@dataclass
class VerificationReport:
    overall_passed: bool
    checks: list[CheckResult]
    started_at: str
    finished_at: str
    db_path: str

class DependencyOverseerVerifier:
    def __init__(self, db, schemas_dir):
        ...

    def verify_strict(self) -> VerificationReport:
        checks = [
            self._check_referential_integrity,
            self._check_active_record_uniqueness,
            self._check_hash_recompute_equality,
            self._check_semantic_hash_propagation,
            self._check_normalization_rule_pinning,
            self._check_build_run_idempotency,
            self._check_closed_enum_membership,
            self._check_open_vocabulary_coverage,
            self._check_vocabulary_canonicalization_integrity,
            self._check_absence_reason_audit,
            self._check_payload_db_equality,
            self._check_kind_registration,
            self._check_pipeline_registration,
            self._check_queue_invariants_heartbeat_based,
            self._check_fencing_token_monotonicity,
            self._check_cascade_bound,
            self._check_defeater_target_typing,
            self._check_claim_canonicalization,
            self._check_belief_network_freshness,
            self._check_answer_shape_rule_trace,
            # Phase 2/3 checks return passed=True with empty failures while scaffold:
            self._check_cross_db_sync,
            self._check_llm_provenance,
            self._check_llm_field_policy,
        ]
        results = [c() for c in checks]
        return VerificationReport(
            overall_passed=all(r.passed for r in results),
            checks=results,
            started_at=...,
            finished_at=...,
            db_path=self.db.path,
        )
```

The wrapper script `scripts/verify_dependency_overseer_contract.py` calls `verify_strict()`, prints a JSON report to stdout, and exits 0 on overall pass and 1 on any failure.

Each check has a precise specification. A representative example:

```python
def _check_semantic_hash_propagation(self) -> CheckResult:
    """
    P27 invariant: a rebuild_queue row exists for an artefact only if its
    semantic_hash changed. Raw-only changes appear in content_hashes history
    but must not produce queue rows.

    Procedure:
      For each (artefact_id, queue_id) in rebuild_queue with state IN ('queued','claimed','building'):
        Read the two most recent content_hashes rows for artefact_id by hashed_at.
        If both rows exist and prior.semantic_hash == latest.semantic_hash:
          Record failure: 'rebuild queued for artefact with unchanged semantic_hash'.
      Return CheckResult(passed = (failures == []), ...).
    """
```

The rendered-page verifier (`verifier_render.py`) is a smaller surface: it loads `ka_article_view.html` with a headless browser (Playwright or equivalent — chosen in implementation), navigates to a sample of article pages, and asserts the checks listed in synthesis §4 rendered-verifier section. Implementation library selection is an open question in §13 below.

## 11. Repair Loop

`src/overseer/repair_loop.py` implements the state machine from synthesis §5:

```python
class RepairLoop:
    def route_verification_failure(self, check_result: CheckResult) -> RepairAction:
        """
        Maps verifier failure to repair action per synthesis §5:
          stale_detected      → enqueue rebuild_queue
          missing_source      → enqueue completion_queue (severity=blocking)
          orphan_edge         → tombstone edge + enqueue completion_queue (severity=medium)
          schema_violation    → tombstone artefact + enqueue completion_queue (severity=high)
          grounding_failure   → (Phase 3 only) tombstone LLM artefact + enqueue
          cross_db_drift      → (Phase 2 only) enqueue cross_db_sync_events + reconcile
          last_mile_failure   → enqueue completion_queue (severity=blocking)
          threshold_exceeded  → move queue row to quarantine + alert
        """

    def execute(self, action: RepairAction) -> None:
        """Apply the action. No write to artefact_registry directly; rebuilds go
        through the queue. Every repair records a row in completion_queue with
        next_action and severity populated."""
```

Promotion (the release gate) is implemented as a separate function that consults the verifier report and the open completion queue:

```python
def can_promote(verifier_report: VerificationReport, db) -> tuple[bool, list[str]]:
    """
    Returns (allowed, blocking_reasons). Blocks if:
      - verifier_report.overall_passed is False
      - any active artefact has freshness_status='stale'
      - any completion_queue row with severity='blocking' has status IN ('open','in_review')
      - any last_mile_production_checks row with status='fail' in the last hour
    """
```

## 12. Phase 1 Test Plan

Each test file asserts one set of invariants. Tests use a temporary SQLite DB seeded from the migration SQL and an in-process worker. No external services.

### `tests/test_overseer_schema.py`

- The migration runs cleanly on an empty DB.
- All 22 tables exist and have the expected columns.
- All CHECK constraints reject out-of-vocabulary values.
- All FOREIGN KEY constraints enforce referential integrity.
- `idx_artefact_active_uniq` is enforced (cannot insert two active rows with the same `(entity_type, entity_id, field_path, schema_version)`).

### `tests/test_overseer_artefact_registry.py`

- Insert succeeds with valid `freshness_status`.
- Insert fails on invalid `freshness_status`.
- `current_fencing_token` defaults to 0 and increments correctly via the claim path.
- `active=0` rows do not conflict with the active-uniqueness index.

### `tests/test_overseer_dependency_edges.py`

- Insert succeeds when both endpoints exist.
- Insert fails when either endpoint is missing (FK).
- Tombstoning a parent leaves the edge row intact for audit.

### `tests/test_overseer_support_sets.py`

- `support_set_hash` recomputes from `members_json`.
- Member rows in `support_set_members` carry `member_hash_at_capture`.
- A support set with a tombstoned member is detected by the verifier.

### `tests/test_overseer_content_hashes.py`

- Inserting a content_hashes row with the same `semantic_hash` as the prior row for the same `artefact_id` is allowed (raw-only change history).
- Inserting with mismatched `normalization_rule_version` across the active set raises the verifier check.
- `compute_raw_hash` and `compute_semantic_hash` are deterministic across processes.

### `tests/test_overseer_normalization.py`

- Whitespace-only changes in a `whitespace_collapsible` field produce identical `semantic_hash`.
- Key reordering in dict content produces identical `semantic_hash`.
- List reordering in an `order_insensitive` list produces identical `semantic_hash`.
- List reordering in an order-sensitive list produces a different `semantic_hash`.
- Cosmetic-only fields are dropped from semantic normalization but retained in raw.
- Case changes in a `case_insensitive` field produce identical `semantic_hash`.

### `tests/test_overseer_vocabulary_registry.py`

- Seeding from `psychopy_seed.json` is idempotent (run twice, same row count).
- Inserting an open-vocab value with the same `(kind, value)` is rejected by UNIQUE.
- A `'synonym'` row must have a `canonical_value` pointing at a `'canonical'` row of the same kind; verifier flags violations.
- Synonym chains of depth > 1 are rejected by the verifier.

### `tests/test_overseer_rebuild_queue.py`

- `claim_one` atomically increments `artefact_registry.current_fencing_token`.
- Two workers cannot claim the same queue row.
- Heartbeat updates `last_heartbeat_at`.
- `complete` moves state to `done`.
- `fail` increments `attempt_count`; at 5 attempts the row moves to `quarantine`.

### `tests/test_overseer_watchdog.py`

- A worker that stops heartbeating for > `heartbeat_timeout_seconds` is reclaimed.
- A worker that keeps heartbeating is not reclaimed, even past the original claim time.
- Reclaim increments `current_fencing_token` on the artefact.
- A reclaimed-then-recovered worker's writes carrying the old fencing token are rejected.

### `tests/test_overseer_invalidation.py`

- Changing one PNU row's `semantic_hash` invalidates exactly the article-epistemic records whose support sets list that PNU row.
- Changing one PNU row's `raw_hash` (semantic unchanged) does **not** enqueue rebuilds.
- Multiple downstream artefacts of one PNU change land as distinct queue rows.

### `tests/test_overseer_cascade_bound.py`

- A simulated PNU registry refresh that touches more than the cascade threshold raises an alert in `completion_queue` with `severity='high'`.
- A normal single-row PNU change does not.

### `tests/test_overseer_completion_queue.py`

- Open items with `severity='blocking'` block promotion.
- Items move from `open` → `in_review` → `resolved` via the repair loop.
- Quarantined items do not auto-retry.

### `tests/test_overseer_data_verifier.py`

- Every check in §10's check list runs and returns a CheckResult.
- The verifier exits 0 when all checks pass.
- The verifier exits 1 when any check fails and identifies the failing rows.
- Each check has a positive fixture (passes) and a negative fixture (fails).

### `tests/test_overseer_repair_loop.py`

- A stale artefact produces a rebuild_queue row.
- A missing-source failure produces a blocking completion_queue row.
- Repair never writes to `artefact_registry` directly; only via the queue.

### `tests/test_overseer_release_gate.py`

- Promotion is blocked if the verifier fails.
- Promotion is blocked if a stale required artefact remains.
- Promotion is blocked if any blocking completion-queue item is open.
- Promotion succeeds when all conditions are clear.

### `tests/test_overseer_render_contract.py`

- Article page renders the epistemic section.
- Stale and missing states render as warnings, not as empty content.
- Provenance badges are visible without hover.
- Production payload hash equals release payload hash for sample records.

### `tests/test_article_epistemic_builder.py`

- The builder produces an `article_epistemic_record` with the required components for a paper that has full input data.
- The builder records `claim_origin` for the primary claim.
- Defeaters carry `target_kind`.
- Answer shape `unknown` is emitted when no rule fires, with `rule_trace_json` populated.
- Re-running the builder with identical inputs produces identical `raw_hash` and `semantic_hash`.
- The builder refuses to write under a mismatched fencing token.

## 13. Acceptance Criteria for Phase 1 Ship

Phase 1 ships when **all** of the following hold:

1. `migrations/overseer_v1__initial.sql` applies cleanly to a fresh DB and to the existing repo DB.
2. The four JSON vocabulary files are present in `schemas/` and pass schema validation.
3. `vocabulary_registry` is seeded from `psychopy_seed.json` (and any extensions added before ship) and the seed-then-reseed test is idempotent.
4. `ArticleEpistemicBuilder` builds an `article_epistemic_record` for every paper that has the required inputs; papers with missing inputs emit a `completion_queue` row with the precise missing-input reason.
5. The single-worker rebuild queue handles claim → heartbeat → complete cleanly. The watchdog reclaims expired-heartbeat claims and the fencing-token mechanism rejects stale writes.
6. `scripts/verify_dependency_overseer_contract.py --strict` exits 0 against a healthy DB and exits 1 with a structured failure list against each seeded negative fixture.
7. `scripts/verify_dependency_overseer_render_contract.py --strict` exits 0 against the rendered article page fixtures.
8. The round-trip proof passes: changing one PNU row's semantic content invalidates exactly the dependent records, enqueues rebuilds, the worker rebuilds them, and the verifier confirms all hashes recompute.
9. The negative round-trip proof passes: a whitespace-only PNU reformat produces a new `raw_hash` but no `semantic_hash` change and no rebuild.
10. All tests in §12 pass on the implementer's machine and in CI.
11. The release gate refuses to promote when any of the documented blocking conditions hold and allows promotion when they are all clear.
12. Documentation: `TASKS.md` and `TOPIC_PROGRESS.md` updated to record the Phase 1 ship; backup script `scripts/backup_databases.py` extended to cover the new overseer tables before ship.

## 14. Open Implementation Questions

These are decisions the implementer makes during Phase 1, not design questions the panel must reconvene on. Each is bounded.

1. **artefact_id generation rule.** Choices: (a) UUID4, (b) content-derived deterministic ID. The synthesis is silent. Recommendation: deterministic ID `{kind}:{entity_id}:{field_path}:{schema_version}` for human-readability; UUID4 only for `build_run_id`, `support_set_id`, `queue_id`, `event_id`, `invocation_id`. Decide at implementation start.
2. **Rendered-verifier headless browser.** Choices: Playwright, Selenium, or HTTP-only HTML parsing. Playwright is the modern default; selection depends on existing repo conventions. Decide at implementation start.
3. **Cascade threshold value.** The synthesis says "cascade beyond the threshold triggers an alert" but does not specify the threshold. Recommendation: 100 dependent artefacts touched by a single source change. Tunable in a config row; revisit at Phase 1 ship after a real-world cascade is observed.
4. **Heartbeat interval/timeout.** Synthesis recommends 30 s interval, 5 min timeout. Confirm in the worker config. Revisit if GC pauses or network jitter cause false eviction.
5. **Schema-version migration cadence.** Open Risk OR7 calls for a quarterly cap on schema-version bumps. Not enforced mechanically; rely on review process.
6. **PsychoPy seed extension cadence.** The seed file is a starting point. Open question: who maintains it and how often does it get re-synced with PsychoPy releases? Recommendation: yearly re-sync, with new instruments added on-demand when papers introduce them.
7. **Empty-set defeater encoding.** When defeaters are absent: choose between (a) zero rows in `defeaters` + absence_reason on the record's defeaters component, or (b) one sentinel row with `target_kind='claim'` and a flag. Recommendation: (a). The verifier check enforces this convention.

## 15. Out-of-Scope Items Worth Naming

These items are part of the dependency overseer's eventual remit but are explicitly **not** in Phase 1. Naming them prevents scope creep.

- Topic pages and DYK cards as artefact kinds (Phase 4).
- Search index freshness tracking (Phase 4).
- Reports/dashboards backed by `build_runs` / `rebuild_queue` (Phase 4).
- Article Finder peer-DB sync (Phase 2).
- LLM-driven content_equivalence_checks (Phase 3).
- LLM-driven vocabulary canonicalization (Phase 3).
- Postgres migration (Phase 4 candidate).
- Multi-worker concurrent rebuilds (Phase 4).
- Backpressure / queue-depth shedding (Phase 4).
- The article-detail UI changes for visible epistemic-layer rendering — covered by the companion contract's Phase 3 work item.

## 16. Closeout

This spec is the engineering contract for Phase 1 of the dependency overseer. When this spec is reviewed and accepted, implementation may begin in the order listed in §13 acceptance criteria.

No code, no migration, and no JSON vocabulary file may land before this spec is accepted. After acceptance, the implementation order is:

1. Land the four JSON vocabulary files in git.
2. Apply the migration.
3. Run the seed script.
4. Implement and test the modules in roughly the order: normalization → hashing → artefact_registry → dependency_edges → support_sets → content_hashes → vocabulary_registry → kinds_registry → pipeline_registry → rebuild_queue → watchdog → completion_queue → build_runs → article_epistemic_builder → verifier_data → repair_loop → last_mile_checks → verifier_render.
5. Run the round-trip and negative round-trip proofs.
6. Run the full test suite.
7. Run both verifiers in strict mode.
8. Update `TASKS.md` and `TOPIC_PROGRESS.md`; extend `scripts/backup_databases.py`.
9. Ship.

Subsequent phases get their own implementation specs.
