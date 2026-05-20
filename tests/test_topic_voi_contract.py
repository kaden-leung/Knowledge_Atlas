import copy
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = REPO_ROOT / "scripts" / "build_topic_voi_payload.py"
VERIFY_PATH = REPO_ROOT / "scripts" / "verify_topic_voi_contract.py"

build_spec = importlib.util.spec_from_file_location("build_topic_voi_payload", BUILD_PATH)
builder = importlib.util.module_from_spec(build_spec)
assert build_spec.loader is not None
build_spec.loader.exec_module(builder)

verify_spec = importlib.util.spec_from_file_location("verify_topic_voi_contract", VERIFY_PATH)
verify = importlib.util.module_from_spec(verify_spec)
assert verify_spec.loader is not None
verify_spec.loader.exec_module(verify)


def test_topic_voi_payload_satisfies_contract():
    errors = verify.validate_payload(
        REPO_ROOT / "data" / "ka_payloads" / "topic_voi.json",
        REPO_ROOT / "data" / "ka_payloads" / "topics.json",
    )

    assert errors == []


def test_builder_creates_ten_target_profile_from_current_payloads():
    payload = builder.build_payload(REPO_ROOT / "data" / "ka_payloads")

    assert payload["contract_id"] == verify.REQUIRED_CONTRACT
    assert payload["method_status"] == "provisional_profile"
    assert set(payload["target_definitions"]) == verify.REQUIRED_TARGETS
    assert payload["topics"]
    first = payload["topics"][0]
    assert set(first["target_vector"]) == verify.REQUIRED_TARGETS
    assert {row["target_id"] for row in first["student_projection"]} == verify.STUDENT_TARGETS
    assert len(first["researcher_projection"]) == 10
    first_target = first["researcher_projection"][0]
    assert payload["score_semantics"] == verify.REQUIRED_SCORE_SEMANTICS
    assert first["score_semantics"] == verify.REQUIRED_SCORE_SEMANTICS
    assert first_target["score_semantics"] == verify.REQUIRED_SCORE_SEMANTICS
    assert first_target["score_components"]
    assert first_target["target_confidence"]["rating"] in verify.ALLOWED_RATINGS
    assert isinstance(first_target["missing_required_signals"], list)
    assert "broad_query" in first_target["article_finder_query"]
    assert "query_test" in first_target["article_finder_query"]


def test_verifier_rejects_missing_article_finder_query():
    payload = builder.build_payload(REPO_ROOT / "data" / "ka_payloads")
    broken = copy.deepcopy(payload)
    first_topic = broken["topics"][0]
    first_target = next(iter(first_topic["target_vector"]))
    del first_topic["target_vector"][first_target]["article_finder_query"]

    tmp = REPO_ROOT / ".pytest_cache" / "broken_topic_voi.json"
    tmp.parent.mkdir(exist_ok=True)
    import json

    tmp.write_text(json.dumps(broken), encoding="utf-8")
    errors = verify.validate_payload(tmp, REPO_ROOT / "data" / "ka_payloads" / "topics.json")

    assert any("article_finder_query is required" in error for error in errors)


def test_verifier_rejects_composite_authority_score():
    payload = builder.build_payload(REPO_ROOT / "data" / "ka_payloads")
    broken = copy.deepcopy(payload)
    broken["topics"][0]["composite_score"] = 0.91

    tmp = REPO_ROOT / ".pytest_cache" / "broken_topic_voi_composite.json"
    tmp.parent.mkdir(exist_ok=True)
    import json

    tmp.write_text(json.dumps(broken), encoding="utf-8")
    errors = verify.validate_payload(tmp, REPO_ROOT / "data" / "ka_payloads" / "topics.json")

    assert any("must not expose a single composite" in error for error in errors)


def test_verifier_rejects_missing_score_semantics():
    payload = builder.build_payload(REPO_ROOT / "data" / "ka_payloads")
    broken = copy.deepcopy(payload)
    first_topic = broken["topics"][0]
    first_target = first_topic["researcher_projection"][0]["target_id"]
    del first_topic["target_vector"][first_target]["score_semantics"]

    tmp = REPO_ROOT / ".pytest_cache" / "broken_topic_voi_score_semantics.json"
    tmp.parent.mkdir(exist_ok=True)
    import json

    tmp.write_text(json.dumps(broken), encoding="utf-8")
    errors = verify.validate_payload(tmp, REPO_ROOT / "data" / "ka_payloads" / "topics.json")

    assert any("score_semantics" in error for error in errors)
