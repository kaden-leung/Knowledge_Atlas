# Dependency Overseer Expert Panel Brief

Date: 2026-05-23
Scope: Knowledge Atlas lifecycle DB, Article Finder, contributed PDFs, PNU refreshes, article-detail epistemic layer, generated payloads, and release gates.

## Purpose

The Knowledge Atlas needs a global dependency-overseer system. The system must know what artefacts exist, what each derived artefact depends on, whether its support set has changed, what must be rebuilt, which verifiers passed, and whether a release may proceed.

This brief defines an expert panel review before implementation. The panel's job is not to approve the idea in general. Its job is to find missing invariants, ambiguous state transitions, false assumptions, and failure modes that would let stale or unsupported content reach production.

## System To Review

The proposed architecture has these core parts:

1. A lifecycle DB that is the source of record.
2. A global artefact registry.
3. A dependency graph between artefacts.
4. Content hashes and support sets for every derived value.
5. Rebuild queues for stale or missing derived artefacts.
6. Verification runs recorded in the DB.
7. Repair/completion loops that run when verification fails.
8. Release gates that do not promote unless dependencies, verifiers, and last-mile production checks pass.
9. Provenance on every component, including explicit LLM provenance where LLMs are used.
10. Formal linkage between Article Finder's local DB and the master lifecycle DB.

The immediate proving ground is the article-detail epistemic layer, especially fields derived from claims, warrants, PNUs, argumentation, Article Finder metadata, and contributed PDFs.

## Non-Negotiable Invariants

The panel should test these invariants and propose additions.

1. No derived artefact is current merely because it exists.
2. A derived artefact is current only if all required support hashes match the hashes used when it was computed.
3. Every derived artefact must have a support set.
4. Every support set entry must name an artefact, not merely a file path or prose description.
5. Every content-producing pipeline must write to the lifecycle DB before deployable JSON is generated.
6. Every verification failure must trigger repair, completion, honest missing-state marking, or a blocking report.
7. Missing source content must not be invented to satisfy a verifier.
8. LLM-generated content must be labelled as synthesis, never as extracted fact.
9. LLM use must record model, prompt ID, prompt hash, input hash, output hash, source fields, and review status.
10. Candidate/contributed PDFs must be tracked before they become accepted Atlas articles.
11. Article Finder's local DB may own operational search state, but the master lifecycle DB owns canonical audit state.
12. A release may not promote if required stale artefacts remain, if JSON diverges from DB-derived content, or if last-mile production checks fail.

## Panel Composition

Use at least six reviewers or simulated reviewers. More is better if the review remains structured.

### Reviewer A: Lead Backend Systems Engineer

Focus:
- schema implementability
- transaction boundaries
- idempotent builders
- failure-safe updates
- migration sequencing

Questions:
- What table or invariant is missing?
- Which state transition can corrupt data?
- Which operations must be atomic?
- Where can a rebuild produce a partial but apparently valid result?

### Reviewer B: Data Pipeline / Workflow Engineer

Focus:
- queue semantics
- stale invalidation
- retry policy
- job claiming
- incremental rebuilds
- backpressure

Questions:
- How are stale artefacts discovered?
- What happens when a dependency changes during a rebuild?
- How are failed rebuilds retried or quarantined?
- How do we avoid rebuilding the world after a small PNU update?

### Reviewer C: Contract / Schema Specialist

Focus:
- JSON schemas
- DB status vocabularies
- verifier contracts
- explicit missing states
- compatibility with generated payloads

Questions:
- Which fields need controlled vocabularies?
- Which missing values are acceptable, and how are they represented?
- Which contracts should fail strict mode?
- Where can the current design silently accept malformed content?

### Reviewer D: Large-System / Platform Architect

Focus:
- global dependency design
- cross-pipeline extensibility
- Article Finder integration
- production promotion gates
- monitoring

Questions:
- Does the model generalize beyond the article page?
- What will break when topics, DYK cards, search, reports, and PNUs all use it?
- What is over-engineered for now?
- What is under-specified for scale?

### Reviewer E: Epistemic / Knowledge-Representation Specialist

Focus:
- claims
- warrants
- backing
- qualifiers
- defeaters
- belief-network relations
- answer-shape selection

Questions:
- Is the epistemic layer being reduced wrongly to the Toulmin layer?
- What support-set evidence is required for each epistemic component?
- Which fields require human review?
- How should uncertainty and source gaps be represented?

### Reviewer F: LLM Governance / Provenance Specialist

Focus:
- LLM-generated enrichment
- source grounding
- hallucination controls
- review queues
- prompt/version audit

Questions:
- Which tasks may use LLMs?
- Which tasks must not use LLMs?
- How do we verify that generated backing or rebuttal prose is supported by input fields?
- What provenance is mandatory before LLM output may be deployed?

## Review Prompts

Each reviewer should answer these questions in order.

1. What invariant is missing?
2. What state transition is ambiguous?
3. What failure would not be detected?
4. What repair loop could corrupt or launder bad data?
5. What should block deployment?
6. What can be repaired automatically?
7. What must be queued for extraction or human review?
8. What is over-engineered?
9. What is under-specified?
10. What is the smallest implementation that proves the design?

## Required Review Targets

The panel must explicitly review these design areas.

### Artefact Identity

Decide how artefacts are named. Examples:

- `PDF-0007.pnu.short_summary`
- `PDF-0007.epistemic.backing`
- `PDF-CANDIDATE-0042.abstract`
- `article_details.payload.PDF-0007`
- `ka_article_view.render_contract.PDF-0007`

Success condition:
- artefact IDs are stable, unique, human-readable, and computable from entity type, entity ID, and field path.

### Support Sets

Every computed value must record the artefacts used to compute it.

Success condition:
- for any derived field, an auditor can answer: "What concrete values was this computed from, and have any changed since?"

### PNU Refresh Dependencies

When PNUs are added or updated, dependent epistemic components must be marked stale.

Success condition:
- a PNU hash change queues rebuilds for only the affected article epistemic components and payloads.

### Article Finder And Candidate PDFs

Candidate/contributed PDFs must be tracked before acceptance.

Required fields include:
- file hash
- title
- abstract
- abstract source
- DOI
- submitter/source
- Article Finder local ID
- relevance score
- duplicate status
- acceptance decision
- linked Atlas paper ID

Success condition:
- a candidate PDF can be traced from upload/search result through extraction, acceptance, generated article record, and article page rendering.

### Abstract Handling

Abstract is a first-class artefact.

Allowed abstract sources:
- `crossref`
- `openalex`
- `publisher_metadata`
- `pdf_extracted`
- `llm_summarized_from_pdf`
- `manual`
- `missing`

Success condition:
- if abstract changes, relevance scoring, classification, science summary, DYK, search index, and epistemic fallback components are marked stale where they depend on it.

### LLM Enrichment

Stage 1 must be deterministic. Stage 2 may use LLMs for enrichment.

LLM-eligible components:
- backing prose
- rebuttal synthesis
- competing-account summary
- answer-shape rationale
- Chinn-Brewer anomaly framing
- plain-language warrant explanation

LLM-prohibited actions:
- inventing evidence
- upgrading confidence
- overwriting extracted claims
- presenting generated synthesis as extracted fact

Success condition:
- every LLM output is grounded to source fields and carries full provenance.

### Verification And Repair

Verification must trigger a loop:

```text
verify -> classify failure -> repair/complete/queue -> reverify -> promote or block
```

Success condition:
- a failed verifier produces either repaired artefacts, completion queue items, honest missing-state records, or a blocking report.

### Release Gate

Promotion must be blocked if:
- required artefacts are stale
- derived artefacts lack support sets
- untracked derived artefacts exist
- JSON payloads diverge from DB-backed content
- LLM provenance is incomplete
- repair queue has blocking failures
- production last-mile checks fail

Success condition:
- staging cannot promote to production unless DB, payload, UI, and production HTTP/rendered checks all pass.

## Panel Output Format

Each reviewer returns:

```markdown
## Reviewer Role

### Verdict
Proceed / Proceed with changes / Do not proceed

### Missing Invariants
- ...

### Ambiguous State Transitions
- ...

### Failure Modes Not Detected
- ...

### Required Schema Changes
- ...

### Required Verifier Changes
- ...

### Required Repair/Completion Changes
- ...

### Minimum Viable Implementation
- ...

### Blocking Concerns
- ...
```

The synthesis pass then produces:

1. accepted invariants
2. rejected suggestions, with reasons
3. final DB schema
4. final verifier contract
5. final repair loop
6. phased implementation plan
7. open risks

## Acceptance Criteria For The Panel Process

The panel process is complete only when:

1. all six reviewer roles have returned structured reviews;
2. every blocking concern has an accepted resolution, deferral, or explicit rejection;
3. the final synthesis names the minimum viable implementation;
4. the implementation spec includes DB migrations, scripts, verifiers, repair loops, monitoring, and release gates;
5. the spec states which parts are deterministic and which may use LLM enrichment;
6. provenance requirements are incorporated into every content table;
7. Article Finder/candidate PDF/abstract dependencies are included;
8. PNU refresh invalidation is included as a worked example;
9. success conditions and last-mile production checks are explicit.

## Recommended Minimum Viable Implementation

Start narrow. Prove the dependency system on article epistemic components and PNU dependencies.

Phase 1:
- create artefact/dependency tables;
- register article details, PNUs, top claims, abstracts, and epistemic components;
- compute hashes;
- detect stale epistemic components when PNU or abstract hashes change;
- queue article-level rebuilds;
- regenerate `article_details.json`;
- verify support hashes and page rendering.

Phase 2:
- add Article Finder local DB sync;
- add candidate PDF artefacts;
- add abstract provenance;
- add accepted-article transition tracking.

Phase 3:
- add Stage 2 LLM enrichment;
- record LLM events and hashes;
- add LLM output verifier;
- add human-review queue.

Phase 4:
- extend the dependency model to topics, DYK cards, search index, reports, and release dashboards.

## Immediate Next Action

Run the panel against this brief and produce:

```text
docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md
```

Do not implement the full dependency overseer until the synthesis has resolved blocking schema and lifecycle questions.
