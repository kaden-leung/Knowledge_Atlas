-- ============================================================================
-- Dependency overseer schema (Phase 1)
-- Date: 2026-05-23
-- Target: Knowledge Atlas lifecycle database, SQLite 3.x
--
-- Source authorities:
--   docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md (controlling)
--   docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md
--   docs/DEPENDENCY_OVERSEER_EXPERT_PANEL_BRIEF_2026-05-23.md
--
-- Scope:
--   * 17 ACTIVE tables: writes land in Phase 1.
--   * 5 SCAFFOLD tables: schema lands; no writes until the activating phase
--     (Phase 2 for cross_db_sync_events; Phase 3 for the four LLM-governance
--     tables).
--
-- Identity model (synthesis P12 / P28):
--   * artefact_id is the LOGICAL identity for every overseer-tracked artefact;
--     recommended construction is {kind}:{entity_id}:{field_path}:{schema_version}.
--   * Active uniqueness is enforced via a partial unique index on
--     (entity_type, entity_id, field_path, schema_version) WHERE active=1.
--
-- Lease and atomicity model (synthesis P1 / P7 / P24):
--   * Multi-table writes run under one transaction.
--   * A claim is valid while the owning worker heartbeat is younger than
--     heartbeat_timeout_seconds; reclaim is driven by the watchdog tick, not
--     a wall-clock lease expiry.
--   * Every claim increments artefact_registry.current_fencing_token; writes
--     carrying a stale fencing_token are rejected at write time (enforced in
--     the worker SQL, not in this DDL).
--
-- Hash model (synthesis P27):
--   * artefact_registry stores raw_hash and semantic_hash; only semantic_hash
--     changes propagate cascade.
--   * content_hashes retains both per build_run, plus normalization_rule_version.
--
-- Vocabulary model (synthesis P26):
--   * Closed enums are enforced by CHECK constraints below; their value lists
--     mirror contracts/schemas/dependency_overseer/status_vocabularies.json.
--   * Open vocabularies (method/measure/instrument/construct/abstract-source)
--     live in vocabulary_registry; columns that store open-vocab values are
--     plain TEXT without CHECK constraints, but the verifier asserts every
--     used value resolves in vocabulary_registry.
--
-- Safety:
--   * Additive only. No existing table is altered or dropped.
--   * Idempotent: every CREATE uses IF NOT EXISTS.
--   * Foreign keys enforced when the init script sets PRAGMA foreign_keys = ON.
-- ============================================================================

PRAGMA foreign_keys = ON;

BEGIN;

-- ----------------------------------------------------------------------------
-- ACTIVE TABLES (writes in Phase 1)
-- ----------------------------------------------------------------------------

-- 1. artefact_registry: the typed artefact registry (synthesis P12, §3 core).
CREATE TABLE IF NOT EXISTS artefact_registry (
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_artefact_active_uniq
    ON artefact_registry(entity_type, entity_id, field_path, schema_version)
    WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_artefact_kind
    ON artefact_registry(kind, active);
CREATE INDEX IF NOT EXISTS idx_artefact_freshness
    ON artefact_registry(freshness_status, kind);

-- 2. dependency_edges: support / derived-from / depends-on edges between artefacts.
CREATE TABLE IF NOT EXISTS dependency_edges (
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
CREATE INDEX IF NOT EXISTS idx_edges_child
    ON dependency_edges(child_artefact_id, edge_kind);

-- 3. content_hashes: per-build hash history (synthesis P27).
CREATE TABLE IF NOT EXISTS content_hashes (
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
CREATE INDEX IF NOT EXISTS idx_content_hashes_semantic
    ON content_hashes(artefact_id, semantic_hash);

-- 4. support_sets: a captured support set with its canonical hash.
CREATE TABLE IF NOT EXISTS support_sets (
    support_set_id     TEXT PRIMARY KEY,
    support_set_hash   TEXT NOT NULL,
    members_json       TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

-- 5. support_set_members: typed support-set members with hash at capture time.
CREATE TABLE IF NOT EXISTS support_set_members (
    support_set_id           TEXT NOT NULL,
    member_artefact_id       TEXT NOT NULL,
    member_hash_at_capture   TEXT NOT NULL,
    PRIMARY KEY (support_set_id, member_artefact_id),
    FOREIGN KEY (support_set_id) REFERENCES support_sets(support_set_id),
    FOREIGN KEY (member_artefact_id) REFERENCES artefact_registry(artefact_id)
);
CREATE INDEX IF NOT EXISTS idx_support_member_lookup
    ON support_set_members(member_artefact_id);

-- 6. build_runs: a build invocation.
CREATE TABLE IF NOT EXISTS build_runs (
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

-- 7. rebuild_queue: rebuilds enqueued by invalidation. Heartbeat-based lease
--    (synthesis P7 / P24); no wall-clock lease_expires_at.
CREATE TABLE IF NOT EXISTS rebuild_queue (
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
CREATE INDEX IF NOT EXISTS idx_queue_state
    ON rebuild_queue(state, severity, first_seen_at);
CREATE INDEX IF NOT EXISTS idx_queue_lease
    ON rebuild_queue(lease_owner)
    WHERE state IN ('claimed','building');

-- 8. worker_heartbeats: liveness-based lease (synthesis P7); P25 progress
--    marker columns populated by Phase 1 workers but acted on only in Phase 2.
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id                          TEXT    PRIMARY KEY,
    last_heartbeat_at                  TEXT    NOT NULL,
    current_claim                      TEXT,
    heartbeat_interval_seconds         INTEGER NOT NULL,
    heartbeat_timeout_seconds          INTEGER NOT NULL,
    progress_marker                    TEXT,
    progress_marker_unchanged_since    TEXT
);

-- 9. artefact_kinds: the kinds-registry. Phase 1 registers three.
CREATE TABLE IF NOT EXISTS artefact_kinds (
    kind_name             TEXT    PRIMARY KEY,
    owner_pipeline        TEXT    NOT NULL,
    support_rule_module   TEXT    NOT NULL,
    schema_version        TEXT    NOT NULL,
    active                INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT    NOT NULL
);

-- 10. pipeline_registry: pipelines that produce overseer artefacts.
CREATE TABLE IF NOT EXISTS pipeline_registry (
    pipeline_name             TEXT PRIMARY KEY,
    version                   TEXT NOT NULL,
    declared_outputs_json     TEXT NOT NULL,
    declared_inputs_json      TEXT NOT NULL,
    last_seen_at              TEXT
);

-- 11. vocabulary_registry: open vocabularies (synthesis P26).
CREATE TABLE IF NOT EXISTS vocabulary_registry (
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
CREATE INDEX IF NOT EXISTS idx_vocab_kind_status
    ON vocabulary_registry(kind, review_status);

-- 12. claims: epistemic claims (companion contract Phase 1 + synthesis P17).
CREATE TABLE IF NOT EXISTS claims (
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
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);

-- 13. defeaters: target-typed defeaters (synthesis P16).
CREATE TABLE IF NOT EXISTS defeaters (
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

-- 14. belief_network_links: PNU-pinned belief-network context (synthesis P19).
CREATE TABLE IF NOT EXISTS belief_network_links (
    record_id            TEXT NOT NULL,
    claim_id             TEXT NOT NULL,
    pnu_id               TEXT NOT NULL,
    pnu_version_hash     TEXT NOT NULL,
    edge_kind            TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    tombstoned_at        TEXT,
    PRIMARY KEY (record_id, claim_id, pnu_id, edge_kind)
);

-- 15. answer_shape_decisions: rule-traced answer-shape assignment (synthesis P18).
CREATE TABLE IF NOT EXISTS answer_shape_decisions (
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

-- 16. completion_queue: global completion items (overseer-wide superset of the
--     companion contract's article_epistemic_completion_queue).
CREATE TABLE IF NOT EXISTS completion_queue (
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
CREATE INDEX IF NOT EXISTS idx_completion_open
    ON completion_queue(status, severity, first_seen_at)
    WHERE status IN ('open','in_review');

-- 17. last_mile_production_checks: production probes (synthesis P15).
CREATE TABLE IF NOT EXISTS last_mile_production_checks (
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

-- ----------------------------------------------------------------------------
-- SCAFFOLD-ONLY TABLES (no writes in Phase 1)
-- ----------------------------------------------------------------------------

-- 18. cross_db_sync_events: Article Finder ↔ lifecycle DB sync (Phase 2).
CREATE TABLE IF NOT EXISTS cross_db_sync_events (
    event_id                    TEXT PRIMARY KEY,
    event_kind                  TEXT NOT NULL CHECK(event_kind IN (
        'accept_candidate','registry_snapshot','tombstone_paper','reconcile_paper'
    )),
    lifecycle_payload_hash      TEXT,
    article_finder_payload_hash TEXT,
    status                      TEXT NOT NULL CHECK(status IN ('pending','matched','unresolved','reconciled')),
    created_at                  TEXT NOT NULL,
    resolved_at                 TEXT
);

-- 19. llm_invocations: Phase 3 LLM call provenance.
CREATE TABLE IF NOT EXISTS llm_invocations (
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

-- 20. prompt_templates: Phase 3 prompt-template registry.
CREATE TABLE IF NOT EXISTS prompt_templates (
    prompt_template_id           TEXT PRIMARY KEY,
    prompt_version               TEXT NOT NULL,
    prompt_template_hash         TEXT NOT NULL,
    allowed_field_policies_json  TEXT NOT NULL,
    created_at                   TEXT NOT NULL,
    active                       INTEGER NOT NULL DEFAULT 1
);

-- 21. source_packets: Phase 3 source-packet manifests with hash pinning.
CREATE TABLE IF NOT EXISTS source_packets (
    source_packet_id      TEXT PRIMARY KEY,
    members_json          TEXT NOT NULL,
    source_packet_hash    TEXT NOT NULL,
    created_at            TEXT NOT NULL
);

-- 22. content_equivalence_checks: Phase 3 LLM-adjudicated semantic equivalence.
CREATE TABLE IF NOT EXISTS content_equivalence_checks (
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

COMMIT;
