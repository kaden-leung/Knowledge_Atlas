# Service-Grade Supervisor Operational Truth

**Date**: 2026-05-27  
**Repo**: `Knowledge_Atlas`  
**Purpose**: define the reusable operational-truth layer that the dependency overseer should use across pipelines and sub-pipelines.

## Principle

The supervisor must not govern by hopeful prose. It must govern by observed operational truth.

That means:
- explicit states
- explicit transitions
- observed heartbeats
- explicit batch or run identity
- explicit attention policies

## Core Distinctions

### 1. Authored state vs. observed state

A component may *say* it is healthy, available, or complete. The supervisor should still distinguish:
- `last_heartbeat_at`: what the component authored
- `last_heartbeat_observed_at`: when the supervisor actually observed it

The second is the more authoritative signal.

### 2. Raw state vs. effective state

Examples:
- raw `running` + stale observed heartbeat -> effective `resume_required`
- raw `failed` -> effective `degraded`
- raw `idle` with fresh observed heartbeat -> effective `idle`

The effective state is what the supervisor should use for control decisions.

### 3. Freshness vs. clock integrity

Not every stale-looking condition is the same.

- `freshness_state` asks whether the supervisor has observed a recent heartbeat.
- `clock_skew_state` asks whether the component-authored timestamp materially disagrees with the observed timestamp.

These are different failure classes and should produce different actions.

## Policy Families

The supervisor should emit actions by policy family, not merely by ad hoc alarm text.

### `worker_availability_policy`
- use when a component appears resumable but is not freshly observed
- example action:
  - `restart_or_resume_component`

### `heartbeat_integrity_policy`
- use when authored and observed time materially diverge
- example action:
  - `inspect_clock_skew_and_checkpoint_truth`

### `component_health_policy`
- use when the component is degraded in a substantive sense
- example action:
  - `repair_or_restart_component`

### `decision_lifecycle_policy`
- use when a decision prompt is raised or acknowledged but not answered
- example action:
  - `answer_decision_prompt`

## Attention Classes

The control plane should classify not only *what* action is needed but *what kind* of urgency it represents.

- `resume_now`
- `inspect_inconsistency`
- `blocked_hard`
- `neglected_too_long`

These should be portable across pipelines.

## Why This Matters

Without these distinctions, the supervisor will confuse:
- old completions with current readiness
- visible activity with productive work
- self-description with operational truth
- stale signals with clock errors

That is precisely how one ends up babysitting intelligent systems instead of supervising them.

## Present Implementation

The current simulator supervisor now embodies this layer in code:
- [operational_truth.py](/Users/davidusa/REPOS/Knowledge_Atlas/sim_supervisor/operational_truth.py)
- [status_report.py](/Users/davidusa/REPOS/Knowledge_Atlas/sim_supervisor/status_report.py)

This is not yet the whole dependency overseer. But it is the correct reusable core:
- state vocabulary
- truth-evaluation logic
- policy-family actions
- machine-readable and human-readable surfaces

## Reuse Standard

Any future pipeline supervisor should, at minimum, expose:

1. raw state
2. observed heartbeat
3. effective state
4. freshness state
5. clock-skew state
6. attention class
7. policy-family action

If it does not, then it is still relying too much on intuition and too little on control-plane truth.
