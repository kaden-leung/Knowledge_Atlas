import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = REPO_ROOT / "data" / "ka_payloads"


def _load(name: str):
    return json.loads((PAYLOAD_DIR / name).read_text())


def test_article_details_are_enriched_with_theory_and_meta_fields():
    payload = _load("article_details.json")
    assert payload["summary"]["article_count"] == 760
    assert payload["summary"]["theory_enriched_article_count"] >= 400
    sample = payload["details"]["PDF-0356"]
    assert sample["article_meta"]["title"]
    assert isinstance(sample["theories"], list)
    assert "argumentation" in sample
    assert "visual_support_gallery" in sample
    assert "technical_results_table" in sample


def test_article_details_keep_technical_result_surface_as_object():
    payload = _load("article_details.json")
    sample = payload["details"]["PDF-0071"]
    technical = sample["technical_results_table"]
    assert isinstance(technical, dict)
    assert technical["title"]
    assert technical["image_url"]


def test_paper_pnus_payload_matches_full_v7_ready_surface():
    payload = _load("paper_pnus.json")
    assert payload["summary"]["source_kind"] == "paper_pnu_artifacts_export"
    assert payload["summary"]["article_count"] == 760
    assert payload["summary"]["short_summary_count"] == 760
    assert payload["summary"]["long_summary_count"] == 760
    assert payload["summary"]["panel_grounded_count"] == 760
    computed_verifier_pass_count = sum(
        1 for row in payload["papers"] if row["pnu"].get("verifier_status") == "pass"
    )
    assert payload["summary"]["verifier_pass_count"] == computed_verifier_pass_count
    assert payload["summary"]["verifier_pass_count"] >= 1
    assert payload["summary"]["papers_with_panel_basis"] == 760
    assert "pnu_artifacts" in payload["summary"]["source_files"]["lifecycle_table"]
    sample = payload["papers"][0]
    assert sample["pnu"]["short_summary"]
    assert sample["pnu"]["panel_status"] == "panel_grounded"
    assert sample["pnu"]["verifier_status"] == "pass"
    assert sample["pnu"]["source_modality"]
    assert isinstance(sample["pnu"]["panel_basis"], list)
    assert "page_refs" in sample["pnu"]


def test_article_details_export_richer_pnu_provenance():
    payload = _load("article_details.json")
    sample = payload["details"]["PDF-0356"]["pnu"]
    assert sample["status"] in {"ready", "not_applicable", "needs_review"}
    assert sample["source_modality"]
    assert sample["generation_method"]
    if sample["status"] == "needs_review":
        assert sample["requires_repair"] is True
        assert sample["verifier_status"] == "fail"
    assert isinstance(sample["panel_basis"], list)
    assert "page_refs" in sample
    assert "page_image_paths" in sample


def test_theories_payload_is_present_and_honest_about_coverage():
    payload = _load("theories.json")
    assert payload["summary"]["source_kind"] == "soft_rebuild_theory_index"
    assert payload["summary"]["theory_count"] >= 300
    assert "intentionally descriptive rather than inferential" in payload["summary"]["coverage_note"]
    sample = payload["theories"][0]
    assert sample["name"]
    assert sample["article_count"] > 0
    assert isinstance(sample["paper_ids"], list)
    assert isinstance(sample["representative_papers"], list)


def test_mechanisms_payload_flattens_existing_manifest():
    payload = _load("mechanisms.json")
    assert payload["summary"]["source_kind"] == "mechanism_profile_manifest"
    assert payload["summary"]["mechanism_count"] == 71
    assert payload["summary"]["framework_count"] == 15
    assert payload["summary"]["cross_framework_count"] == 15
    sample = payload["mechanisms"][0]
    assert sample["id"]
    assert sample["name"]
    assert sample["kind"] in {"framework_specific", "cross_framework"}
