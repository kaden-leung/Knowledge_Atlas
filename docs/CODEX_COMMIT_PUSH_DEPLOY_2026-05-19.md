# Codex — Commit, Push, and Server-Deploy Instructions (Knowledge_Atlas)

*David Kirsh, 2026-05-19. Supplements `Article_Eater_PostQuinean_v1_recovery/docs/CODEX_COMMIT_AND_PUSH_GUIDANCE_2026-05-18.md` (the cross-AI commit discipline memo) with Knowledge_Atlas-specific deploy mechanics. Read both: the Article_Eater memo for the commit discipline that applies across all three repos, this one for the deploy step that only Knowledge_Atlas needs.*

---

## Scope

This document covers the full path from "code change in a working tree" to "students see the change at `https://xrlab.ucsd.edu/ka/`". The three-step path:

```
local working tree → commit → push to origin/master → deploy to VM at /var/www/xrlab/ka/
```

Codex is expected to handle steps 1 and 2 unattended when DK has given branch-scoped authorisation; step 3 requires DK approval each time unless the change is a documented routine deploy class (see §6 below).

---

## §1. Commit discipline

The Article_Eater memo `CODEX_COMMIT_AND_PUSH_GUIDANCE_2026-05-18.md` is the authoritative reference. The five rules summarised here:

1. **Commit immediately for cross-AI work.** When CW, AG, or Codex hand off pending state to another agent, commit first. Never leave another agent to inherit an uncommitted working tree.
2. **Never push to `main`/`master` without DK approval.** This rule binds every agent. Push to a feature branch (`codex/feature-name-YYYY-MM-DD`) and let DK rebase or merge.
3. **Respect other agents' in-progress files.** If a file is modified or untracked and not yours, leave it alone. Note it in the commit message ("did not touch X.html — appears to be CW's in-progress work").
4. **Commit message style.** One-line summary, blank line, wrapped paragraph(s) describing the change in prose. Reference task IDs from `TASKS.md` (UJ-X, POE-EXT-X, PQ-X, etc.) when the work resolves or advances a tracked task.
5. **Pre-commit checks before every commit.** Run the project's contract verifiers and at minimum the affected test files. See §3.

### Branch naming convention

For Knowledge_Atlas specifically:

- `codex/<feature-or-fix>-YYYY-MM-DD` — Codex's working branches.
- `cw/<feature-or-fix>-YYYY-MM-DD` — CW's working branches (rare; CW usually commits to `master` directly per DK convention, but this branch pattern is for multi-step refactors).
- `ag/<feature-or-fix>-YYYY-MM-DD` — AG's working branches.
- Never commit to `master` unless the change is small and CW-scoped, AND CW has DK's standing authorisation for `master` commits in the relevant area.

---

## §2. The current pending state (as of 2026-05-19)

Before any new Codex work, the pending state needs to clear:

- `master` is **46 commits ahead of `origin/master`** and **2 commits behind**. The 2 origin commits need to be pulled and rebased onto local before push.
- There are uncommitted changes in `master`: the journey map, the two wireframe stubs, the t1-t4 intro edits, the POE-* docs, and the TASKS.md update from the 2026-05-19 session.
- A stale `.git/index.lock` has been observed; if encountered, run `rm /Users/davidusa/REPOS/Knowledge_Atlas/.git/index.lock` (no process should be holding it at the time).

Codex should NOT advance any Knowledge_Atlas work until DK has resolved this pending state. The expected DK action sequence:

```bash
cd /Users/davidusa/REPOS/Knowledge_Atlas
rm -f .git/index.lock                               # only if the lock is stale
git status                                          # confirm what's pending
git add <expected files>                            # the 2026-05-19 session's changes
git commit -m "<message from CW's 2026-05-19 hand-off>"
git fetch origin
git rebase origin/master                            # or merge, DK's preference
# resolve any conflicts; the 2 origin commits are likely Codex's substitution-v7-lite work
git push origin master                              # the moment of authorisation
```

Until this completes, every new Codex commit on `master` adds to the backlog rather than landing on origin.

---

## §3. Pre-commit checks

Before every Codex commit on Knowledge_Atlas:

```bash
cd /Users/davidusa/REPOS/Knowledge_Atlas

# 1. Verify the subscription-AI contract is not violated.
python3 scripts/verify_subscription_ai_only_contract.py --strict

# 2. Verify the DYK authoring contract.
python3 scripts/verify_dyk_llm_authoring_contract.py --strict

# 3. Run the affected test files.
pytest -q tests/test_dyk_llm_authoring_contract.py \
            tests/test_subscription_ai_contract.py \
            tests/test_substitution_skill_contract.py \
            tests/test_v7_lite_contract.py \
            tests/test_v7_async_worker_contract.py \
            tests/test_cross_page_journey_contract.py \
            tests/test_site_runtime_smoke.py

# 4. Compile-check Python files Codex touched.
python3 -m py_compile <each touched .py file>

# 5. If HTML files were touched, run the link-and-anchor smoke test.
python3 scripts/check_html_links.py 160sp/  # if the script exists; otherwise spot-check
```

Any failing check aborts the commit. A failing test that Codex believes is a false positive should be reported in the commit message but NOT silenced; CW or DK adjudicates.

---

## §4. Push procedure

Once a commit (or batch of commits) is ready to push and DK has authorised:

```bash
cd /Users/davidusa/REPOS/Knowledge_Atlas

# 1. Confirm you're on the right branch (feature branch or, with DK authorisation, master).
git status
git branch --show-current

# 2. Sync with origin.
git fetch origin

# 3. Rebase or merge if behind.
git rebase origin/master           # preferred for clean history on feature branches
# OR
git merge origin/master            # if rebasing would require rewriting shared commits

# 4. Resolve any conflicts. If conflict resolution requires creative choices,
#    STOP and message DK rather than guessing.

# 5. Run the pre-commit checks again post-rebase. Conflict resolution can re-introduce
#    issues the original commits didn't have.
python3 scripts/verify_subscription_ai_only_contract.py --strict
python3 scripts/verify_dyk_llm_authoring_contract.py --strict
pytest -q tests/

# 6. Push.
git push origin <branch>           # feature branch
# OR with DK approval:
git push origin master             # master

# 7. Confirm push succeeded.
git log --oneline origin/<branch>..HEAD     # should print nothing
```

If the push is rejected (typically because someone else pushed first), repeat from step 2.

---

## §5. Server deploy

Once `origin/master` carries the change, students will NOT see it until the deploy script runs on the VM. The VM serves `/var/www/xrlab/ka/`, which is a separate checkout of the repo from DK's local working tree.

### Standard deploy

```bash
# 1. SSH to the VM. Replace <vm-host> with the actual hostname.
ssh dkirsh@<vm-host>

# 2. Move to the VM checkout.
cd /var/www/xrlab/ka

# 3. Pull the latest master.
git pull origin master

# 4. Run the deploy script.
bash scripts/deploy_to_vm.sh

# 5. Verify the deploy.
python3 scripts/server_verify_served_tree.py

# 6. Tail the server log briefly to confirm no startup errors.
tail -n 50 logs/ka_server.log
```

The deploy script:

- Refreshes the Python virtualenv at `.venv/` if dependencies changed.
- Restarts the KA server process (pidfile at `ka_server.pid`).
- Updates `ka_config.js` if the host or port changed.
- Logs to `logs/deploy_YYYY-MM-DD_HHMMSS.log`.

### Routine deploy class (Codex-authorised)

DK has standing authorisation for Codex to run the deploy script for these change classes:

1. **Static content updates** — markdown docs, talk outlines, sitemap updates, journey map content, syllabus week-detail fills. No code change.
2. **DYK payload updates** — `data/ka_payloads/did_you_know_llm_overrides.json` updates that pass `verify_dyk_llm_authoring_contract.py --strict`.
3. **Other payload updates** — `data/ka_payloads/articles.json`, `topic_ontology.json`, `evidence.json` regenerations that pass the relevant contract verifiers.

DK approval per-deploy is required for:

- Any change to `*.py` runtime code.
- Any change to `ka_canonical_navbar.js`, `ka_user_type.js`, `ka_config.js`.
- Any change to `ka_auth_server.py`, the auth schema, or the auth payloads.
- Any change to `scripts/deploy_to_vm.sh` itself or to `scripts/server_release_cycle.sh`.
- The first deploy of any new HTML page that adds a new route.

### Rollback

If a deploy breaks the served tree:

```bash
ssh dkirsh@<vm-host>
cd /var/www/xrlab/ka
git log --oneline -5                    # find the last-known-good commit
git reset --hard <last_good_sha>
bash scripts/deploy_to_vm.sh
python3 scripts/server_verify_served_tree.py
```

After rollback, fix the broken change in DK's local working tree, push the fix, and run a fresh deploy. Do NOT push from the VM checkout — the VM is a one-way mirror, and writing back to origin from there creates merge conflicts.

---

## §6. Routine deploy classes — autonomous Codex authorisation

DK has stated that Codex may run the full sequence (commit → push → deploy) without per-step approval for these classes of work:

1. **DYK payload regeneration after AG's V7-complete run.** Once AG's 800-paper pass produces a new `did_you_know_llm_overrides.json`, Codex commits the change, pushes, and deploys, provided the contract verifier passes `strict` and the consolidation script's diff summary is logged in the commit message.

2. **Topic ontology refreshes after AG's substitution-graph extraction pass.** Same idea: structured data, contract-verified, Codex routes it through.

3. **Wireframe-to-HTML promotions when CW signs off in writing.** When CW produces a markdown content document (e.g. `ka_vr_measurability_content_2026-05-18.md`) and asks Codex to render it to a live HTML page, Codex commits the HTML, runs the link-and-anchor smoke test, pushes, and deploys.

4. **Auto-generated payload rebuilds via `scripts/build_ka_adapter_payloads.py`.** Provided the script exits 0 and no schema validators fail.

For anything outside these classes, Codex commits and pushes with a clear ask in the commit message ("DK: please review and deploy") and does NOT run the deploy script.

---

## §7. The relationship between this repo, Article_Eater, and atlas_shared

Knowledge_Atlas is the front-end-and-content repo. Article_Eater is the pipeline-and-extraction repo. atlas_shared is the schemas-and-contracts repo. Most Codex work happens in one repo at a time; cross-repo changes require coordination notes in the commit messages of all affected repos.

When a Codex change touches Knowledge_Atlas plus another repo:

1. Commit and push the Knowledge_Atlas side first (read-side).
2. Commit and push the other repo (write-side or schema-side).
3. Note in both commit messages that the changes are paired and reference each other's SHAs.

When in doubt, prefer two commits over one, even within a single repo. Cross-AI debugging is easier when commits are small.

---

## §8. Common mistakes

1. **Forgetting to fetch before push.** Always `git fetch origin` first. The remote may have advanced.
2. **Pushing to master without explicit DK approval.** This is the single hardest rule and the one Codex has slipped on in the past. When in doubt, push to a feature branch.
3. **Running the deploy script with uncommitted changes in the VM working tree.** The VM tree should be clean. If it isn't, `git status` will show the drift; reset to `origin/master` before deploying.
4. **Deploying without running the post-deploy verifier.** The deploy script does not verify the served tree by itself. The `server_verify_served_tree.py` script is the gate; run it every time.
5. **Treating `data/ka_payloads/*.json` as code.** It's data. Payload commits get one-line subjects describing the regeneration, not detailed prose. The verifier is the gate.
6. **Editing files in `160sp/ka_live_snapshot/`.** Don't. That directory is a frozen historical mirror per `CLAUDE.md`. Edits there will be overwritten on the next snapshot refresh.
7. **Committing the operator-local `ka_server_snapshot.*` files.** These should never be tracked; they're per-operator.

---

## §9. When AG runs the V7-complete DYK pass

The specific sequence when AG completes the 800-paper run and the new DYK payload is ready:

```bash
# AG side: at the end of the run, the consolidation script has produced
# data/ka_payloads/did_you_know_llm_overrides.json with the full card set.

# Codex picks up. From the Knowledge_Atlas working tree:
cd /Users/davidusa/REPOS/Knowledge_Atlas

# 1. Pull AG's payload commit (AG commits to its own branch in Article_Eater,
#    but the consolidation script writes to Knowledge_Atlas; the change shows
#    up as an uncommitted modification here).

# 2. Verify the contract.
python3 scripts/verify_dyk_llm_authoring_contract.py --strict

# 3. Run the smoke test for the DYK browser surface.
pytest -q tests/test_dyk_llm_authoring_contract.py tests/test_dyk_payload.py

# 4. Stage and commit.
git add data/ka_payloads/did_you_know_llm_overrides.json
git commit -m "data(dyk): consolidate AG V7-complete run cards

AG's 800-paper V7-complete pass produced ~1,000 new DYK cards. Consolidated
into the production payload alongside the existing 50 CW-repaired cards.

Coverage: <IV × DV breakdown from the run log>
Total cards: <N>
Contract: passes strict
Run id: v7_complete_2026-05-19"

# 5. Push (this is in the routine-deploy class per §6).
git push origin master

# 6. Deploy.
ssh dkirsh@<vm-host>
cd /var/www/xrlab/ka
git pull origin master
bash scripts/deploy_to_vm.sh
python3 scripts/server_verify_served_tree.py
```

After the deploy completes, the DYK browser surface (`https://xrlab.ucsd.edu/ka/160sp/ka_did_you_know_browser.html` if it exists, otherwise wherever Track 4 has placed it) will serve the new cards. Refresh, spot-check three or four cards from different topic clusters, and the run is complete.

---

## §10. What this document does not cover

- The Article_Eater repo's commit and push procedures — see the 2026-05-18 memo.
- The atlas_shared repo's release cycle — defer to DK.
- The grading-server deployment (under `160sp/grader_page/`) — separate runtime, separate deploy.
- Backup and disaster-recovery procedures for the VM — DK's responsibility, not Codex's.

If any of these become Codex's responsibility, a follow-up memo will specify the procedures.

---

*End of memo. The next session that uses this document should reference it by date (`CODEX_COMMIT_PUSH_DEPLOY_2026-05-19.md`); the convention is that revisions get a new dated file rather than in-place edits, so the historical instructions remain traceable.*
