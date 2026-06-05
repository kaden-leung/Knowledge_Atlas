"""Deterministic CI checks for the Track 2 Task 3 submission."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SCORE = re.compile(r"\*\*Score:\*\*\s*(\d+)\s*/\s*75")


def _tracked_task3_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "Track 2/Task 3", ".github/workflows/track2.yml"],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return [
        REPO / item.decode()
        for item in result.stdout.split(b"\0")
        if item
    ]


def check_grader(min_score: int) -> int:
    command = [
        sys.executable,
        "160sp/autograders/t2_task3_grader.py",
        "Track 2/Task 3",
        "kaden-leung",
    ]
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
    output = result.stdout + result.stderr
    print(output, end="")
    match = SCORE.search(output)
    failures: list[str] = []
    if result.returncode != 0:
        failures.append(f"grader exited {result.returncode}")
    if not match or int(match.group(1)) < min_score:
        failures.append(f"grader score is below {min_score}/75")
    if "Contract Gate:** ✅ Passed" not in output:
        failures.append("contract gate did not pass")
    if "Script exited with code" in output or "can't open file" in output:
        failures.append("ruthless helper reported an execution error")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


def check_links() -> int:
    broken: list[str] = []
    checked = 0
    for md_path in ROOT.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            target = target.split("#", 1)[0].strip()
            if not target:
                continue
            checked += 1
            resolved = (md_path.parent / unquote(target)).resolve()
            if not resolved.exists():
                broken.append(f"{md_path.relative_to(REPO)} -> {target}")
    if broken:
        print("\n".join(f"FAIL: broken link {item}" for item in broken))
        return 1
    print(f"PASS: {checked} local Markdown links checked")
    return 0


def check_artifacts() -> int:
    forbidden_names = {
        "PR_BODY.md",
        "peer_review_prompt.txt",
        "track2_ruthless_prompt_artifact.md",
        "pasted-text.txt",
        "policy_clearance.json",
        "human_review_log.json",
        "knowledge_atlas.db",
    }
    forbidden_fragments = (
        "/Users/" + "big" + "daddy",
        "BEGIN " + "OPENSSH PRIVATE KEY",
        "BEGIN " + "RSA PRIVATE KEY",
    )
    secret_patterns = (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),)
    env_secret = re.compile(
        r"SERPAPI_KEY\s*=\s*['\"]?([A-Za-z0-9_-]{16,})",
        re.IGNORECASE,
    )
    failures: list[str] = []
    for path in _tracked_task3_files():
        if path.name in forbidden_names or "acquired_pdfs" in path.parts:
            failures.append(f"forbidden tracked artifact: {path.relative_to(REPO)}")
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for fragment in forbidden_fragments:
            if fragment in text:
                failures.append(
                    f"forbidden local/secret text in {path.relative_to(REPO)}: {fragment}"
                )
        for pattern in secret_patterns:
            if pattern.search(text):
                failures.append(
                    f"possible secret in {path.relative_to(REPO)}: {pattern.pattern}"
                )
        for match in env_secret.finditer(text):
            value = match.group(1).lower()
            if value.startswith(("your_", "replace_", "example_", "mock_")):
                continue
            failures.append(
                f"possible SERPAPI_KEY value in {path.relative_to(REPO)}"
            )
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: tracked-file artifact and secret scan")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    grader = sub.add_parser("grader")
    grader.add_argument("--min-score", type=int, default=68)
    sub.add_parser("links")
    sub.add_parser("artifacts")
    args = parser.parse_args(argv)
    if args.command == "grader":
        return check_grader(args.min_score)
    if args.command == "links":
        return check_links()
    return check_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
