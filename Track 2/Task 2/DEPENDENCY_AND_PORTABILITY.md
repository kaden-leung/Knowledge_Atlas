# Task 2 Dependency and Portability Note

## What Is Portable

These grading paths work from the PR checkout:

```bash
python3 160sp/autograders/t2_task2_grader.py "/path/to/Track 2/Task 2" kaden-leung
cd "Track 2/Task 2"
python3 gap_extractor.py --help
```

The root `gap_results.json` and `query_results.json` files are committed so grading does not require live Article Eater execution.

## What Requires Sibling Dependencies

Full gap extraction requires Article Eater service modules:

- `services.voi_search`
- `services.web_of_belief`
- `services.web_of_belief_components.enums`
- the Article Eater template corpus

This is an explicit dependency, not a hidden assumption. The root `gap_extractor.py --help` path is self-contained so the official grader can verify the entry point without installing the full sibling stack.

## Class-Grading Boundary

For class grading, the committed artifacts are the deliverables:

- `gap_results.json`
- `query_results.json`
- `Phase 2/gap_results.json`
- `Phase 3/query_results.json`
- contracts and verification docs

For production use, this code should be packaged with the Article Eater dependency set or moved into the Article Eater repository where the services package naturally exists.
