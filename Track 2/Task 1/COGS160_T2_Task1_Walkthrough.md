# COGS 160 — Track 2, Task 1: The Full Walkthrough

**Assignment:** Fix the Contribute Page  
**Student:** Kaden Leung  
**PR:** https://github.com/dkirsh/Knowledge_Atlas/pull/9  
**Date:** 2026-05-18

---

## How to use this document

This document has three parts. Each one covers the same project, going one level deeper.

- **Part 1** is pure English — no code, no jargon. Read it to get the story.
- **Part 2** introduces vocabulary and design decisions. It always refers back to Part 1 by name.
- **Part 3** is the technical detail — code, before/after, exact numbers. It refers back to Parts 1 and 2.

You can stop after any part. If someone asks you a general question, Part 1 is enough. If the instructor asks you to explain a design decision, Part 2 is enough. If they ask you to walk through specific code, Part 3 has it.

---

# Part 1 — The Plain Story

## 1. What is Knowledge Atlas?

Knowledge Atlas is a curated research database. It stores roughly 1,400 peer-reviewed academic papers about how physical environments affect the way people think, feel, and behave. The questions it tries to answer sound like: does more natural light in an office make people more focused? Does ceiling height change how creative someone is? Does background noise in a classroom raise stress levels?

It is not a general academic search engine like Google Scholar. It is deliberately narrow — only papers that meet a specific standard of evidence get in. That curation is the point. A researcher who needs to know "what does the science actually say about acoustics and cognition?" can come to Knowledge Atlas and trust that everything there has been vetted.

The site was built and run by the instructor, with students contributing research each quarter. Track 2 students — Article Finders — are responsible for finding new papers and submitting them for review. This is what the contribute page is for: it is the public front door through which anyone can suggest a paper.

When the system works end-to-end, the journey of a submitted paper looks like this:

1. A person drops a PDF onto the contribute page and clicks Submit.
2. The PDF travels over the internet to the Knowledge Atlas server.
3. The server checks: is this a real PDF? Is it already in the database? 
4. A classifier — an automated expert reviewer — reads the paper and decides: is this relevant to architecture and cognition? What type of paper is it? What topic does it cover?
5. Depending on the verdict, the paper lands in one of three places: a queue for human reviewers if it looks good, a holding area if the classifier isn't sure, or a rejection pile if it clearly doesn't belong.
6. A reviewer makes the final call. If approved, the paper eventually gets extracted into the Atlas.

The contribute page was the very first step in this chain. It was broken. This assignment was to fix it.

---

## 2. The broken suggestion box

Open the contribute page in a browser and it looks completely functional. There's a drag-and-drop PDF zone. There's a text field for the citation. There's a "why this matters" field and an optional email. You drop a PDF, type a citation, click "Send suggestion," and a thank-you message appears: "Your suggestion is being reviewed."

Nothing happened.

Here is what the code actually did when you clicked Submit:

1. It read the **filename** of your PDF — just the name, like `paper.pdf`. Not the contents. Not the actual bytes of the file.
2. It packed that filename together with your text fields into a small note.
3. It saved that note to `localStorage` — a tiny private notepad that lives in your own browser on your own computer. No one at Knowledge Atlas can see it. It disappears when you close the tab.
4. It waited 500 milliseconds — half a second — and then opened the thank-you modal. It did this **no matter what happened**. Even if saving to localStorage failed. Even if you submitted a blank form. The thank-you always appeared.

Think of it like a restaurant that gives you a comment card, a pen, and a drop box — but the drop box is actually a hole that leads directly into your own pocket. You write your feedback, drop it in, it falls back into your coat, and a cheerful voice says "Thank you for your feedback!" The restaurant never sees a word.

There were two things that needed to be built to make the system work:

**Connection A:** The form needed to actually send the PDF — the real bytes, not just the filename — over the internet to the Knowledge Atlas server.

**Connection B:** The server had the code for a classifier sitting inside it, imported and ready, but the part of the server that handled incoming submissions never actually called it. The classifier was present but ignored.

Both connections were missing. Building them is what this assignment was.

---

## 3. Four rooms, no hallways

To understand why those two connections were the whole problem, it helps to picture the system as four separate rooms in a building.

**Room 1: The Web Form**
This is the public front door. Anyone can walk in. It collects a PDF and some text from the user. Its only job is to receive what someone gives it and pass it along to Room 2.

**Room 2: The Server**
This is the mailroom. When a package arrives, it checks: is this actually a PDF (not a renamed Word document in disguise)? Has this exact paper been submitted before? If it passes those checks, the server saves the PDF to a holding area — a quarantine folder — and writes a record to a filing system. Then it is supposed to hand the paper to Room 3 for review.

**Room 3: The Classifier**
This is the expert reviewer in the back office. It has no phone and no door to the street — it can only receive papers from Room 2. It reads the title, abstract, and text of a paper and makes two decisions: what *type* of paper is this (an experiment, a review of the literature, a theoretical argument?), and what *topic* does it belong to in the Atlas (daylight and cognition, ceiling height and creativity, noise and stress?). It hands back a verdict with a confidence score.

**Room 4: The Database**
This is the permanent filing cabinet. Every paper that comes through the system gets a record here — what it is, what the classifier thought of it, what status it has, what happened to it.

Before this assignment, the building existed. All four rooms were built and furnished. But the hallways between them were not installed. Room 1 (the form) was not connected to Room 2 (the server) — clicking Submit sent data to the user's own browser instead of across the internet. Room 2 (the server) received papers but never walked them down to Room 3 (the classifier) — papers went straight from the mailroom to the filing cabinet without ever being reviewed.

This assignment installed both hallways.

---

## 4. Why you can't just tell the AI to build the hallways

If you asked an AI assistant "build the connection between the form and the server," it would produce code in minutes. Plausible-looking code. Code that might even appear to work on a quick test. Here is why that is not enough on its own, and why three more phases existed.

**Problem 1: The AI tests its own work.**
When an AI writes code and then writes tests for that code, it tends to test the thing it just built — not the thing you actually need. It is like a student who writes both the exam and the answer key. The exam will be easy, the student will get 100%, and you will have learned nothing about whether they understood the material. Real verification means someone else designs the test.

**Problem 2: The AI is confident about things it hasn't verified.**
An AI will say "the classifier is now being called on every submission" in a tone that sounds completely certain. If you don't check the actual code, you might believe it. In this project, after Phase 3 integration, every single verification question found at least one thing the AI had said it did but hadn't quite done correctly. Not because the AI was lying — it genuinely believed its description was accurate. But descriptions and implementations drift.

**Problem 3: The AI fixes more than you asked.**
Without a precise spec, an AI filling in the blanks will make choices. Some of those choices introduce problems you didn't anticipate. The contract — written in Phase 2 before any code was produced — defined exactly what "working" meant, which made it possible to check whether the code matched the definition rather than just whether it seemed reasonable.

The four-phase structure of this assignment — diagnose, spec, build, verify — is the antidote to all three of these problems.

---

## 5. Phase 1: Diagnose — read before you touch

Before writing a single line of code, the first phase was to read all three programs carefully and understand what each one does, what it does not do, and what is missing between them.

The web form was about 40 lines of JavaScript. Reading it carefully revealed the localStorage dead-end — the form was never calling `fetch()`, which is the function a web page uses to send data over the internet. Without `fetch()`, no data ever leaves the browser.

The server was several thousand lines of Python. Reading it revealed something surprising: the classifier was already imported at the top of the file — the code that calls the classifier existed in other parts of the server — but the specific function that handles incoming paper submissions went from receipt to storage without ever invoking it.

The classifier itself was a separate package, entirely self-contained. It could accept a paper's text and produce a verdict. It just had no way to receive files from the internet on its own — it needed the server to hand things to it.

These three readings produced two deliverables: a boxology diagram (a box-and-arrow picture of the data flow, including the missing pieces) and a gap statement (one paragraph saying exactly what existed, what was missing, and what needed to be built). Both became the foundation for everything that followed.

---

## 6. Phase 2: Write the contract

Before writing any code, a contract was written. Think of it like a song brief that a producer receives before they start recording: "three minutes, key of E minor, tempo 120 BPM, the bridge comes at 2:15, the vocal needs to cut through on earbuds." Without that brief, the producer might deliver something great — but it might be in the wrong key, the wrong length, or sound perfect on studio monitors and terrible on a phone.

The contract specified:

- **What goes in:** a PDF file, a citation text, or both.
- **What comes out:** a JSON response telling the submitter what happened to each paper — whether it was accepted, flagged for review, or rejected, and why.
- **The five statuses:** a paper could land in exactly one of five states — staged for review (accepted), needs human review (edge case), rejected because it's off-topic, rejected because the file wasn't a real PDF, or rejected because it was already in the database.
- **Storage rules:** accepted papers get saved to a quarantine folder and a database record. Rejected papers get a database record but no saved file.
- **What "correct" means for test cases:** four specific papers were defined, with their expected outcomes written down before any tests were run.
- **Rules that could never be broken:** fourteen invariants — things like "if a paper is rejected, it must not appear in the quarantine folder" and "every submitted paper must appear in the audit log."

The contract was 959 lines long. It existed so that when something didn't work later, you could look at the contract and say "this is a spec problem" (the contract allowed for something it shouldn't have) versus "this is an implementation problem" (the code didn't do what the contract required). That distinction turned out to matter a lot in Phase 4.

---

## 7. Phase 3: Six questions that caught fifteen bugs

After Phase 3 integration — after the code was written to build both hallways — the work was not done. The code was handed back to the AI and it was asked six targeted questions. Not "does this work?" — that question gets a yes whether or not anything works. Six specific questions about specific risks.

Think of this like the QA checklist a mixing engineer runs before delivering a track. Not "does it sound good?" — of course the engineer thinks it sounds good. The checklist asks: does the bass still hold on earbuds? Does any vocal moment clip above 0dB? Does the fade work on streaming platforms that cut silence? These are targeted checks for specific failure modes.

Here are the six questions and what each one found:

**Q1: Where exactly does the PDF get saved, and what happens if the folder doesn't exist?**
Found: if the disk was full or the folder couldn't be created, the server would crash with a 500 error AND silently lose the paper ID — allocating a number that would never be used again. Fixed by wrapping the file write in error handling that records the failure instead of crashing.

**Q2: Show me the exact line where the classifier is called and what data it receives.**
Found three bugs: the title extraction was picking up the journal banner instead of the actual title. The abstract extraction couldn't handle multi-line abstracts. The paper's own ID was being passed as an empty string instead of the real ID. All three fixed.

**Q3: Show me where you write to the database and what happens if the paper ID already exists.**
Found the most serious bug in the project — a race condition. The code was generating IDs by counting existing rows (`SELECT COUNT(*) + 1`). Under normal conditions this works. But if two papers are submitted at the exact same moment, both see the same count, both compute the same ID, and one of them crashes. Also found that if paper #5 was deleted, the next submission would reuse ID #5 — potentially attaching its history to a ghost. Fixed by adding a dedicated counter table that increments atomically — one indivisible operation that cannot be interrupted.

**Q4: What happens when the classifier says it needs more information before deciding?**
Found: the classifier has a field called `next_action` that says things like "I need the abstract before I can decide" or "a human should review this — I'm not confident." The routing code was completely ignoring this field. If the classifier said "please send this to a human reviewer" but also returned `verdict=accept` and a high confidence score, the code would accept the paper automatically. Fixed by adding a check: certain `next_action` values override the verdict and force human review.

**Q5: How do you tell an accepted paper from an edge case in the database?**
Found: the classifier's opinion — its verdict, article type, topic, and confidence score — was never being saved to the database. It was present in the HTTP response sent to the browser, but not stored. A reviewer looking at the database tomorrow would see a paper flagged for review but have no idea what the classifier thought about it. Fixed by saving the classifier's full output into a `validation_notes` field on every paper record.

**Q6: If I submit five PDFs in one session, do I see all five results or just the last one?**
Found three bugs: the file input only accepted one file at a time. If you drag-dropped five files, it silently kept only the first one and discarded the rest. Each time results appeared, they wiped out the previous results — only the most recent submission was visible. Fixed by enabling multi-file input, passing all files to the server in one request, and making results accumulate rather than replace.

Fifteen bugs total. Fourteen were fixed. One was declined by design: the submitter's "why this matters" notes were not passed to the classifier. The reasoning was that classifier evidence should be the paper's content, not the submitter's framing — the notes are kept for reviewers but not for the classifier.

---

## 8. Phase 4: Four papers, one failure, one fix

With the code written and the bugs fixed, the next step was to run four specific test papers through the live system and record what happened.

**Test 1:** An acoustics paper about how the built environment affects sound perception. Expected to be accepted as on-topic. The system accepted it, saved the PDF to the quarantine folder, and created a database record. Pass.

**Test 2:** A machine learning paper about drug efficacy and oncology — completely outside the Atlas's scope. Expected to be rejected as off-topic. On the first run: the system flagged it as an "edge case" and routed it to a holding queue instead of rejecting it. Fail.

**Test 3:** A theoretical architecture paper about symbolic interaction. Expected to be an edge case sent to human review. The system sent it to human review. Pass.

**Test 4:** A citation-only submission — no PDF, just text describing a paper about hybrid fuel cell vehicles. Expected to skip the classifier entirely and go to human review. The system handled it correctly. Pass.

First run: 3 of 4. One failure to diagnose.

The failure on Test 2 was a mismatch between what the classifier can do and what the routing code expected. The classifier's knowledge bank contains only positive topics — things that belong in the Atlas — and no negative topics. So when it encountered a clearly off-topic paper (oncology and drug efficacy), it tried to find the closest match in its topic bank and settled on "Color Psychology" with a confidence score of 0.26. Then it said `verdict=edge_case` — not quite sure.

The routing code at that point sent all edge cases to the human review queue. The contract expected this paper to be rejected as off-topic. The question was: is this a spec problem or an implementation problem?

**The diagnosis:** it was a spec limitation. The classifier would never be able to say "confidently off-topic" because its knowledge bank has no off-topic entries to match against. Any paper from a different field would land in this same low-confidence edge-case zone. The right fix was not to change the classifier — that was out of scope — but to add a rule at the routing layer: if a paper comes back as an edge case *and* its best topic match scores below 0.40 (meaning even the best guess is very weak), treat it as off-topic and reject it.

After the fix, the second run: 4 of 4. All tests pass.

---

## 9. The submission

With the code verified and the tests passing, the work moved to submitting it through GitHub.

**Forking:** The Knowledge Atlas repository belongs to the instructor. To submit work, a copy of it — called a fork — was created under the student's own GitHub account. Work happens on the fork; the submission is a request to merge the fork's changes back into the instructor's version.

**The diff problem:** While the branch was being worked on, the instructor added some files to the main repo — Track 2 and Track 3 starter files. Our branch had been created before those additions, so comparing it to the current main repo showed them as "deleted" — even though we had never touched them. Before submitting, the branch needed to be rebased — replayed on top of the current main repo — so the comparison showed only what actually changed.

**The email problem:** Every git commit is stamped with a name and email address from your computer's git configuration. Pushing those commits to a public GitHub repo would have exposed the UCSD email address permanently in the public commit history. GitHub blocked the push as a privacy protection. The fix was to rewrite all 23 commits to use a noreply alias that GitHub provides — `kaden-leung@users.noreply.github.com` — which shows your username in the commit but keeps the actual email private. The rewrite is safe because these commits had never been pushed anywhere before.

**The PR:** A pull request is a formal request to merge your branch into someone else's repository. It shows the diff, includes a description, and lets the instructor review and grade the work. The PR was opened against `dkirsh/Knowledge_Atlas:master`.

---

# Part 2 — The Design Decisions

*Each section in Part 2 opens by referring back to a Part 1 section, then introduces vocabulary and explains why things were designed the way they were.*

---

## 1. The five statuses (from Part 1 §2 and §6)

In Part 1 we described a paper landing in one of five places. Here is what those places are called in the code and what each one means technically.

| Status | What it means | File saved? |
|---|---|---|
| `staged_pending_review` | Classifier accepted it; waiting for a human to confirm | Yes — in quarantine folder |
| `needs_review` | Classifier was uncertain, or flagged it for human attention | Yes, if a PDF was submitted — no file for citation-only submissions |
| `rejected_off_topic` | Paper doesn't belong in this Atlas | No |
| `rejected_bad_file` | File was not a real PDF (magic-byte check failed) | No |
| `duplicate_existing` | This paper is already in the database | No |

Every paper that enters the system lands in exactly one of these. The contract's job was to specify exactly which input conditions produce which status — so there was no ambiguity when writing or checking the code.

The distinction between `staged_pending_review` and `needs_review` is subtle but important: a `staged` paper is one the classifier was confident about; a `needs_review` paper is one the classifier flagged for human attention (uncertain, or explicitly asked for more information). Both get saved; both go to a reviewer. The classifier's opinion is preserved in both cases so the reviewer knows why it was flagged.

---

## 2. What the classifier outputs (from Part 1 §3)

In Part 1 we described the classifier as the expert reviewer in the back office. Here is what it actually produces when it finishes reading a paper.

The classifier returns a structured result with five key fields:

- **`verdict`**: the overall decision — `accept`, `edge_case`, or `reject`.
- **`classifier_article_type`**: what kind of paper it is — empirical experiment, literature review, theoretical argument, meta-analysis, etc. Think of this like the genre tag on a streaming platform — the classifier is tagging each submission.
- **`primary_topic`**: which Atlas topic the paper best matches — "Daylight and Cognition," "Thermal Comfort," "Biophilia," etc. The Atlas has a constitution bank of topic definitions, each with a list of keywords and inclusion/exclusion terms. The classifier scores the paper against every topic and picks the best match.
- **`overall_confidence`**: a number between 0.0 and 1.0. 0.95 means "very confident." 0.26 means "barely guessing." Below 0.72, the system flags the paper for human review regardless of the verdict.
- **`next_action`**: what the classifier recommends doing next. Options include "ready for downstream extraction," "needs a human reviewer," "I need the abstract before I can decide," and "go extract the PDF text and call me again." This field exists because the classifier knows what evidence it has and can request more.

The classifier never makes a final decision — it informs one. A human reviewer can override anything the classifier says. The classifier's job is to do the first pass so the reviewer doesn't have to read every paper from scratch.

---

## 3. The routing decision tree (from Part 1 §7)

In Part 1 we described the routing as the missing hallway between the server and the classifier. Here is how that hallway actually decides where a paper goes.

Think of it like a triage nurse's protocol. The nurse sees hundreds of patients. For each one, they run through a decision tree: vital signs? if unstable → immediate care. Breathing? if compromised → respiratory team. Pain level? if high → fast-track. The protocol is not "is the patient sick?" — it's a sequence of specific checks that map evidence to action.

The routing function checks things in this order:

1. **Did validation fail?** (not a real PDF, file too large) → `rejected_bad_file`. Stop.
2. **Is it a duplicate?** (same SHA-256 hash, same DOI, same title) → `duplicate_existing`. Stop.
3. **Is it citation-only with very little text?** (under 100 characters) → skip the classifier, go to `needs_review`.
4. **Is it an edge case with a very weak topic match?** (`verdict=edge_case` AND topic confidence below 0.40) → `rejected_off_topic`. This is the fix from Phase 4.
5. **Does the classifier say to send it to human review?** (`next_action` is "needs abstract," "review borderline case," etc.) → `needs_review`, regardless of what `verdict` says.
6. **Did the classifier reject it?** → `rejected_off_topic`.
7. **Did the classifier say edge case with a reasonable topic match?** → `needs_review`.
8. **Did the classifier accept it with high confidence?** → `staged_pending_review`.

Step 4 is the fix from the Test 2 failure (off-topic detection). Step 5 is the fix from Q4 (the `next_action` override). The off-topic check runs first because an edge case with a very weak topic match should be rejected immediately — the `next_action` override is checked after, for cases where the topic match is plausible but the classifier still wants a human to decide.

---

## 4. Why the contract was the scaffold (from Part 1 §6)

In Part 1 we said the contract defined what "working" meant before the code existed. Here is why its specific contents mattered.

The contract had three structural components:

**Invariants** — statements that must always be true after every operation. Example: "If a paper has status `staged_pending_review`, a file must exist on disk at the quarantine path, and the SHA-256 hash of that file must match what's in the database." This invariant made it impossible to accidentally accept a paper without saving its file.

**The JSON schema** — a machine-readable definition of what a valid API response looks like. Every field is named, every field has a type, required fields are marked as required. This meant the response could be checked automatically, not by eyeballing it.

**Test cases** — eight specific test scenarios, each with exact expected outcomes. Test 1: submit an on-topic PDF → it must be `staged`. Test 7: submit a clearly off-topic PDF → it must be `rejected_off_topic`, must have no quarantine file. These were written before the code was written, so the pass/fail criteria couldn't be adjusted to match what the code happened to do.

The combination meant that every bug found during verification was unambiguously a bug — not a matter of interpretation. The contract said what should happen; the code either did it or didn't.

---

## 5. The six questions as risk categories (from Part 1 §7)

In Part 1 we listed the six verification questions as a sequence of discoveries. Here is what category of risk each one was designed to surface.

| Question | Risk category | Why it matters |
|---|---|---|
| Q1: Where does the PDF get saved? | **Storage failure** | A system that loses files silently looks functional until you check the folder |
| Q2: What gets passed to the classifier? | **Garbage in, garbage out** | If the evidence is wrong, the classification is meaningless even if the code runs |
| Q3: What happens in the database? | **Concurrency and integrity** | Race conditions only appear under load; they look like random crashes, not bugs |
| Q4: What does the code do with `next_action`? | **Silent ignoring** | The most dangerous bugs are the ones that don't crash — they just quietly do the wrong thing |
| Q5: How do you distinguish accepted from edge case? | **Auditability** | If you can't reproduce the classifier's reasoning tomorrow, you can't trust the database |
| Q6: Five PDFs in one session? | **Multi-item edge cases** | The happy path (one file, no errors) is never the only path |

The point of asking these specific questions rather than "does it work?" is that "does it work?" gets an answer of yes even when it doesn't. These six questions force an honest accounting of exactly how the code behaves in each scenario.

---

## 6. The off-topic detection fix (from Part 1 §8)

In Part 1 we said Test 2 failed because the system put an oncology paper in the review queue instead of rejecting it. Here is the technical explanation of why and how it was fixed.

The classifier knows only positive topics — things that belong in the Atlas. It has no negative-topic mechanism. So when it receives a clearly off-topic paper, it does not say "this paper is about drug efficacy" — it says "this paper best matches Color Psychology with 26% confidence." That 0.26 score is its way of saying "I can't find anything good."

The routing code at the time sent all `edge_case` verdicts to human review. This was technically correct for genuine edge cases — papers that are plausibly adjacent to the Atlas's scope. But it was incorrect for papers that are simply foreign to the Atlas's vocabulary. A human reviewer should not have to read oncology papers.

The fix: a threshold at the routing layer. If verdict is `edge_case` and the best topic confidence is below 0.40 — meaning even the classifier's best guess is weak — route to `rejected_off_topic` instead of `needs_review`. The 0.40 number was chosen conservatively: the failed paper scored 0.26 (well below), and a paper that is genuinely adjacent to the Atlas would be expected to score above 0.50. The gap between 0.26 and 0.50 leaves room for the threshold to be wrong without causing harm in either direction.

This was classified as a spec limitation rather than an implementation bug — the classifier's constitution bank having no negative-evidence mechanism is a known limitation, not a code error. The fix is a compensating control at the routing layer, with the threshold documented as tunable.

---

## 7. The git work (from Part 1 §9)

In Part 1 we described forking as making a copy and rebasing as replaying your changes on top of an updated version. Here is what that means technically.

A **fork** in GitHub is a full copy of a repository linked to the original. Changes on the fork do not affect the original until you explicitly request a merge — that request is the pull request.

A **branch** is a separate line of development within a repository. The branch for this submission was `track/2-staging/kaden-leung`. All 23 commits were on this branch, not on `master`.

**Rebasing** is the operation that became necessary because the branch was created from commit `ea942bb`, but by submission time the instructor's master had advanced to `7fb7539` — two new commits that added Track 2 and Track 3 starter files. Without rebasing, the pull request diff would show those files as "deleted by this PR" — because they existed on master but not on our branch. After rebasing, the 23 commits are replayed on top of the current master, and the diff shows exactly what we added and changed with nothing spurious.

**The email rewrite** was needed because git stamps each commit with the author's email address — in this case, the UCSD email `k7leung@ucsd.edu`. GitHub's privacy protection blocks pushes that would expose a private email in a public repository. Rather than disabling the protection, all 23 commits were rewritten to use the noreply alias `kaden-leung@users.noreply.github.com`. This preserves the commit history and authorship but keeps the actual email address private.

---

# Part 3 — The Technical Detail

*Each section refers back to Part 2 by name, then shows the actual code.*

---

## A. The classifier internals (from Part 2 §2)

In Part 2 we described the classifier as producing five output fields. Here is how it produces them.

### Evidence stages

Before classifying, the classifier assesses how much information it has. It assigns a stage:

- `bibliographic_only` — title, authors, year only
- `metadata_text` — also has abstract or keywords
- `pdf_surface_light` — also has first-page text
- `extraction_aware` — also has sections, IV/DV measurements

The stage determines how hard the classifier works. More evidence → more confidence → more specific routing.

### Topic scoring (the constitution bank)

The Atlas has a master list of topic definitions — each topic has a name and a set of keyword patterns and exclusion terms. For every submitted paper, the classifier runs its text against every topic definition and computes a score. Score formula for topic overlay matching:

```
score = 0.24 (base)
      + 0.12 × (number of keyword hits)
      + 0.08 (if the topic label itself appears in the text)
      - 0.12 × (number of exclusion term hits)
      capped at 0.96, threshold at 0.20 to count at all
```

The topic with the highest score becomes `primary_topic`. The score becomes `primary_topic_confidence`.

### Article type classification

The classifier scans the full text blob for signal phrases. "Systematic review," "meta-analysis" → review paper. "Participants were randomly assigned," "between-subjects design" → empirical study. "We propose a framework," "theoretical account" → theoretical paper. The first type to cross a confidence threshold wins.

### The 0.72 routing threshold

Papers with `overall_confidence < 0.72` go to `needs_review` regardless of verdict. This is the routing layer's "uncertain — escalate to human" rule, equivalent to the triage nurse saying "I'm not sure, get the doctor." 0.72 was chosen as the boundary between "classifier is confident" and "classifier is guessing."

---

## B. The database bugs (from Part 2 §5 — concurrency risk)

In Part 2 we described Q3 as the concurrency risk question. Here are the actual bugs and fixes.

### Bug 1: The race condition (SELECT COUNT + 1)

**Before:**
```python
def _next_id(prefix: str) -> str:
    row = db.execute(f"SELECT COUNT(*) FROM articles").fetchone()
    n = row[0] + 1
    return f"{prefix}-{n:06d}"
```

**Why it's a bug:** If two requests arrive at the same millisecond, both read `COUNT(*) = 5`, both compute `n = 6`, both try to insert `KA-ART-000006`, one succeeds, one crashes with a 500 error and the user gets no response. Under any real load this will happen.

**After — atomic counter table:**
```sql
CREATE TABLE IF NOT EXISTS id_sequences (
    prefix  TEXT PRIMARY KEY,
    counter INTEGER NOT NULL
);
```
```python
def _next_id(prefix: str, table: str, id_col: str) -> str:
    row = db.execute(
        "UPDATE id_sequences SET counter = counter + 1 "
        "WHERE prefix = ? RETURNING counter", (prefix,)
    ).fetchone()
    return f"{prefix}-{row[0]:06d}"
```

The `UPDATE … RETURNING` is atomic in SQLite — it increments the counter and reads the new value in one uninterruptible operation. Two concurrent requests will serialize: one gets 6, the other gets 7. No collision possible.

### Bug 2: IntegrityError crash

**Before:** If the UNIQUE constraint on `article_id` was ever violated (e.g., from a pre-existing row), the INSERT raised an unhandled exception → 500 to the client.

**After:**
```python
try:
    _do_insert(article_id)
except sqlite3.IntegrityError:
    article_id = _next_id("KA-ART")  # get a fresh ID
    _do_insert(article_id)            # retry once
```

### Bug 3: ID reuse after deletes

**Before:** `SELECT COUNT(*) + 1` reuses IDs after rows are deleted. Delete article #5, next ID is #5 again. Any audit log entries from the old #5 now appear to belong to the new #5.

**After:** The `id_sequences` counter only ever increases. Once counter = 5 is used, the next ID is 6 regardless of whether article #5 still exists.

---

## C. The routing function (from Part 2 §3)

In Part 2 we described the triage decision tree. Here is the implementation.

```python
_NEXT_ACTIONS_NEEDING_REVIEW = frozenset({
    "need_abstract_or_keywords",
    "extract_pdf_surface",
    "review_borderline_case",
})

_OFF_TOPIC_PRIMARY_TOPIC_THRESHOLD = 0.40

def _route_classifier_verdict(verdict, overall_confidence: float,
                               next_action, primary_topic_score):
    # Step 4: off-topic detection — edge case with weak topic match (runs first)
    if verdict == "edge_case" and primary_topic_score < _OFF_TOPIC_PRIMARY_TOPIC_THRESHOLD:
        return "rejected_off_topic"

    # Step 5: next_action override — classifier explicitly requests human review
    if next_action in _NEXT_ACTIONS_NEEDING_REVIEW:
        return "needs_review"

    # Step 6: confident reject
    if verdict == "reject":
        return "rejected_off_topic"

    # Step 7: edge case with plausible topic match
    if verdict == "edge_case":
        return "needs_review"

    # Step 8: accept — check confidence
    if overall_confidence < 0.72:
        return "needs_review"

    return "staged_pending_review"
```

The off-topic check runs before the `next_action` override — a paper that matches no Atlas topic at all should be rejected immediately, regardless of what `next_action` says. The function is pure: no database reads, no side effects. Given the same inputs it always returns the same output, which made it easy to unit-test with 11 cases before any live server tests ran.

---

## D. The frontend: before and after (from Part 2 §1)

In Part 2 we described the five statuses that now show up in the results panel. Here is what changed in the JavaScript.

### Before — the localStorage dead-end

```javascript
async function submitSuggestion() {
    const payload = {
        filename: chosenFile ? chosenFile.name : null,  // filename only, no bytes
        citation: document.getElementById('citation').value,
        submitted_at: new Date().toISOString()
    };
    localStorage.setItem("ka.public_suggestions",
        JSON.stringify(payload));          // saves to browser only
    setTimeout(() => {
        document.getElementById('__ka_thanks').setAttribute('open', '');
    }, 500);                               // thank-you modal always fires
}
```

### After — the fetch() connection

```javascript
async function submitSuggestion() {
    const fd = new FormData();
    chosenFiles.forEach(f => fd.append("files", f));   // actual PDF bytes
    fd.append("citations", citationEl.value);
    fd.append("notes", whyEl.value);
    fd.append("source_surface", "ka_contribute_public");

    submitBtn.disabled = true;
    try {
        const resp = await fetch(apiBase + "/api/articles/submit",
                                 { method: "POST", body: fd });
        const data = await resp.json();
        renderResults(data);               // show cards in results panel
    } catch (err) {
        showError("Submission failed — please try again.");
    } finally {
        submitBtn.disabled = false;        // always re-enable
    }
}
```

Key changes: `FormData` carries the actual file bytes. `fetch()` sends them over the internet. The modal is gone — results appear inline in the page. On any failure (network error, server error), an error message appears and the button re-enables. `localStorage` is never written.

---

## E. Hard question 1: Walk me through the off-topic failure

*This traces Test 2 — the ML/oncology paper — end-to-end through the system.*

1. `Cell_Reports_Methods.pdf` is submitted via the contribute page. `FormData` carries the bytes to the server.
2. Server validates: magic bytes `%PDF-` — pass. Size — pass.
3. SHA-256 hash checked against database — not a duplicate — pass.
4. PDF text extracted. `_classify_article_payload` is called with the paper's title, abstract, and text.
5. Classifier runs. Constitution bank has no oncology or pharmacology topics. Best match: "Color Psychology" at score 0.26.
6. Classifier returns: `verdict="edge_case"`, `primary_topic="Color Psychology"`, `primary_topic_confidence=0.26`, `overall_confidence=0.58`.
7. `_route_classifier_verdict("edge_case", 0.58, "ready_for_intake_decision", 0.26)` is called.
8. Step 4 fires: `verdict == "edge_case"` AND `0.26 < 0.40` → return `"rejected_off_topic"`.
9. Server writes a database row with `status="rejected_off_topic"`, `quarantine_path=NULL`.
10. No PDF file is saved to disk.
11. Audit log records `action="rejected_off_topic"`.
12. Response returned: `status="rejected_off_topic"`, `routing_reason="off_topic:edge_case_with_weak_topic_match_0.26_below_0.4"`.
13. Frontend renders a grey "Rejected — off-topic" card.

---

## F. Hard question 2: Did the classifier work correctly?

*How to distinguish spec bugs (classifier quality) from implementation bugs (routing code).*

Test 1's paper (`Building_Environment.pdf`, an acoustics study) was correctly routed to `staged_pending_review` — the routing logic worked. But the classifier's output had two quality issues:

- `classifier_article_type = "meta_analysis"` — the paper is empirical, not a meta-analysis.
- `primary_topic = "Biophilia"` — the paper is about urban acoustics, not biophilia.

These are **spec bugs** (classifier quality limitations), not **implementation bugs**. The routing code did exactly what it was supposed to do given the classifier's output: `verdict=accept`, `confidence=0.82 (above 0.72)` → `staged_pending_review`. The routing was correct.

The classifier's wrong article type and wrong topic are a reflection of the constitution bank's coverage and the heuristic's signal phrases — they require improvements to `atlas_shared` itself, which was outside the scope of this PR. The contract documented them as "spec bug / classifier coverage" in the diagnosis notes (D1).

The key principle: **routing correctness** (did the paper land in the right bucket given what the classifier said?) is separate from **classification accuracy** (did the classifier correctly identify the paper's type and topic?). This PR was responsible for the former. The latter is the classifier's own accuracy problem.

---

## G. Hard question 3: Walk me through Q3 (the database race condition)

*A complete walkthrough of the concurrency bug — question asked, bug found, fix designed, fix verified.*

**The question asked:** "Show me where you write to the database. Which table? What values go in each column? What happens if the paper ID already exists?"

**Reading the code:** `_next_id("KA-ART")` is called before the INSERT. It runs `SELECT COUNT(*) FROM articles` and returns `COUNT + 1` formatted as `KA-ART-000006`.

**The bug identified:** Under concurrent load, two requests run `SELECT COUNT(*)` simultaneously. Both read 5. Both compute 6. Both attempt `INSERT INTO articles (article_id=KA-ART-000006, ...)`. The first succeeds. The second hits a UNIQUE constraint violation — `IntegrityError` — and the server returns a 500 error to that client. The paper is lost. Additionally, the counter has "used up" an ID without creating a row, so ID 6 is gone forever. If article #3 was ever deleted, the next insert would reuse `KA-ART-000003`, silently inheriting that old row's audit history.

**The fix designed:** A dedicated `id_sequences` table with a single row per prefix. The counter is updated with `UPDATE id_sequences SET counter = counter + 1 WHERE prefix = 'KA-ART' RETURNING counter` — one atomic operation that reads and increments in one move. SQLite guarantees this cannot be interrupted by another connection. A concurrent request that arrives at the same moment will queue behind it and get counter = 7.

**The fix verified:** 
- Counter test: wiped `articles`, seeded counter at 3, submitted a paper → received `KA-ART-000004`. No reuse.
- Concurrency test: `xargs -P10` burst of 10 simultaneous POSTs → received 10 distinct IDs (`KA-ART-000005` through `KA-ART-000014`), all monotonic, zero collisions, zero 500 errors.
- Collision test: manually inserted `KA-ART-000099` into the database (simulating an out-of-band collision), then submitted → first INSERT failed → retry fetched counter=100 → `KA-ART-000100` inserted successfully. No crash, no data loss.

---

**Quick reference — where each rubric item lives in the repo:**

| Rubric item | File |
|---|---|
| Diagnosis (boxology + gap) | `160sp/contracts/Track_2_Context.md` |
| Spec (contract) | `160sp/contracts/CLASSIFIER_INTEGRATION_CONTRACT_2026-05-09.md` |
| Security review (R-2 supplement) | `160sp/contracts/SECURITY_REVIEW_2026-05-19.md` |
| Verification questions | `160sp/verification_log.md` |
| Validation 4/4 PASS + supplementary | `160sp/validation_matrix.md` |
| File manifest | `160sp/MANIFEST.md` |
| Per-rubric-line completion checklist | `160sp/COMPLETION_CHECKLIST_2026-05-19.md` |
| Grader pre-run report | `160sp/rubrics/t2/GRADE_REPORT.md` |

---

## Addendum (2026-05-19) — eight improvements after peer-PR review

After PR #9 was opened on 2026-05-18, the work in [`Track 2/PEER_PR_COMPARISON_2026-05-19.md`](../PEER_PR_COMPARISON_2026-05-19.md) ruthlessly compared our work against two peer PRs (Dhruv Sood #1, Julie Issasnek #6). The comparison surfaced a handful of specific gaps where peers either had a deliverable we lacked or had a test case we hadn't run. Eight targeted improvements were made on top of the original 23-commit submission, all verified to keep the grader auto-tests at 8/8 → 15/15.

**Brief catalog (each shipped as a separate commit on this branch):**

- **Improvement A** — Run TC-3, TC-4, TC-5, TC-8 from our own contract §8 against the live endpoint. Results documented in `validation_matrix.md` §"Supplementary contract validation". All 4 PASS. Closes the gap where our contract specified 8 TCs but we'd documented only 4. *(commit `82ea30d`)*
- **Improvement B** — Add `160sp/contracts/SECURITY_REVIEW_2026-05-19.md` — 14-section security audit (S1-S14) with file:line citations. Zero high-severity vulnerabilities. Matches Dhruv's `task1_security_review.md` and adds an R-2 supplement we previously lacked. *(commit `0cbad7e`)*
- **Improvement C** — Submit 20 additional PDFs (10 from `Part_One_10pdfs/` + 10 from `Part 2 Pdfs/`) to the live endpoint. Documented in `validation_matrix.md` §"Expanded validation". Every routing branch exercised; 0 server crashes; 20/20 routing decisions contract-conformant. *(commit `2d23dce`)*
- **Improvement D** — Add `160sp/COMPLETION_CHECKLIST_2026-05-19.md` — per-rubric-line DONE/DEFERRED audit. Mirrors Dhruv's `task1_completion_checklist.md` with citations to our specific lines and commits. *(commit `07dd992`)*
- **Improvement E** — Persist `contact_email` and `submitter_citation_hint` in `validation_notes` JSON for both PDF and citation-only paths. Closes a soft data-loss issue: the contribute form had an email field that was being read into JS but dropped before reaching the server. Source: Dhruv's bug review §B4 surfaced the same gap. *(commit `91e09ac`)*
- **Improvements F + G + H** (one frontend bundle) — UX polish on `ka_contribute_public.html`:
  - F: color-coded left borders + verdict badges per status (teal/amber/red/grey)
  - G: visual confidence bar replacing the plain "Confidence: 0.82" row
  - H: collapsible `<details>`-driven "Why this verdict?" section surfacing routing reason + verdict + next_action + topic confidence + backend
  All three reuse the existing XSS-safe `textContent`/`createElement` pattern — every dynamic value still passes through `textContent`, no `innerHTML` introduced. *(commit `af932f8`)*

**Final state at the time of this addendum:**

- 29 commits on branch (was 23 before improvements)
- 24 files changed vs `origin/master`, 4499 insertions, 81 deletions
- Grader: 8/8 PASS → 15/15 (verified after each improvement, not just at the end)
- Validation evidence: 4 rubric papers + 4 contract TCs + 20 expanded papers = 28 validated submissions
- No high-severity security findings (per `SECURITY_REVIEW_2026-05-19.md`)
- 100% Track 2 Task 1 scope — no peer-style scope creep into other tracks

*End of document.*
