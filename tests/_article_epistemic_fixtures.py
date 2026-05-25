"""Synthetic article-detail records used by the article_epistemic test suite.

Each factory function returns one record shaped like an entry in
`data/ka_payloads/article_details.json[details]`. They are intentionally
minimal — only the fields the Stage 1 builder reads.

Spec §14 fixture list (one factory per case):
  * complete_record
  * partial_record_missing_primary_claim
  * record_with_attack_count_no_defeaters
  * record_with_stale_pnu
  * abstract_only_record
  * candidate_pdf_unverified_record
  * record_with_long_claim_text
  * record_with_llm_generated_content   (rejected by Stage 1)
"""

from __future__ import annotations

from copy import deepcopy


def _base_pnu_fresh() -> dict:
    return {
        "status": "verified",
        "short_summary": "Short PNU summary.",
        "long_summary": "Long PNU summary.",
        "short_status": "ready",
        "long_status": "ready",
        "panel_status": "panel_grounded",
        "panel_basis_count": 3,
        "panel_basis": [],
        "source_modality": "page_images_only",
        "generation_method": "deterministic",
        "theory_mechanism_status": "not_applicable",
        "verifier_status": "pass",
        "verifier_error_count": 0,
        "requires_repair": False,
        "page_refs": [],
    }


def _base_article_meta(title: str = "Test Article") -> dict:
    return {
        "title": title,
        "year": 2025,
        "doi": "10.1234/test.0001",
        "article_type": "empirical",
        "primary_topic": "indoor environment",
        "sample_n": 50,
        "venue": "Test Journal",
        "authors": "Doe, J.",
        "apa_citation": "Doe (2025) Test paper.",
        "main_conclusion": "A clear main conclusion.",
    }


def _base_science_summary() -> dict:
    return {
        "core_finding": "A clear core finding.",
        "methods_and_design": "Lab experiment.",
        "key_statistics": "p < .05",
        "design_implications": "Some implications.",
        "limitations": "Some limitations.",
        "gap_and_door": "Future work.",
        "word_count": 500,
        "summary_source_modality": "extracted",
        "page_image_policy": "n/a",
        "passed_verification": True,
    }


def complete_record(paper_id: str = "TEST-COMPLETE") -> dict:
    return {
        "paper_id": paper_id,
        "top_claims": [
            {
                "finding": "Temperature increased subjective comfort by 0.8 points.",
                "signal": "Direct Measured Result",
                "warrant": "Empirical Association",
                "credence": 0.9,
                "support_count": 3,
                "attack_count": 0,
                "qualifier": "specified",
            },
            {
                "finding": "Lighting had a smaller effect than temperature.",
                "signal": "Comparison Result",
                "warrant": "Empirical Association",
                "credence": 0.75,
                "support_count": 1,
                "attack_count": 0,
                "qualifier": "specified",
            },
        ],
        "argumentation": {
            "claim_count": 5,
            "contradiction_count": 0,
            "dominant_stance": "supports",
            "node_qualifier": "",
            "search_target_count": 0,
            "support_edge_count": 4,
            "attack_edge_count": 0,
        },
        "evidence_profile": {
            "atlas_credence_mean": 0.82,
            "atlas_credence_percentile": 70,
            "paper_claim_count": 5,
            "support_edge_count": 4,
            "attack_edge_count": 0,
            "contradiction_count": 0,
            "search_target_count": 0,
            "dominant_stance": "supports",
        },
        "pnu": _base_pnu_fresh(),
        "article_meta": _base_article_meta("Complete Record Example"),
        "science_summary": _base_science_summary(),
        "constructs": [],
        "instruments": [],
        "operationalization": {},
        "technical_results_table": {},
        "theories": [],
        "supporting_papers": [],
        "contradicting_papers": [],
        "related_papers": [],
        "atlas_reading": {},
        "visual_support_gallery": {},
    }


def partial_record_missing_primary_claim(paper_id: str = "TEST-NO-PRIMARY") -> dict:
    rec = complete_record(paper_id)
    rec["top_claims"] = []
    rec["article_meta"]["main_conclusion"] = ""
    rec["science_summary"]["core_finding"] = ""
    return rec


def record_with_attack_count_no_defeaters(paper_id: str = "TEST-ATTACK-NOFIX") -> dict:
    rec = complete_record(paper_id)
    # Argumentation reports attacks but no contradicting papers / defeater rows.
    rec["argumentation"]["attack_edge_count"] = 4
    rec["argumentation"]["contradiction_count"] = 0
    rec["argumentation"]["dominant_stance"] = "mixed"
    # The primary claim itself carries the per-claim attack_count so the
    # evidence_strength component records a non-zero attack_count, which is
    # what triggers count reconciliation.
    rec["top_claims"][0]["attack_count"] = 4
    rec["contradicting_papers"] = []
    return rec


def record_with_stale_pnu(paper_id: str = "TEST-STALE-PNU") -> dict:
    rec = complete_record(paper_id)
    rec["pnu"]["status"] = "verified"
    rec["pnu"]["requires_repair"] = True
    rec["pnu"]["verifier_status"] = "fail"
    rec["pnu"]["verifier_error_count"] = 2
    return rec


def production_typical_record(paper_id: str = "TEST-PROD-TYPICAL") -> dict:
    """The shape 758 of 760 production records actually have: full extraction
    (claims, argumentation, evidence) but a PNU row flagged requires_repair, so
    the record is stale / show_with_warning with a blocking queue item.

    This — not complete_record — is the modal production record. The suite
    previously asserted only the fresh-PNU happy path, which occurs in 0/760
    records (panel finding); this fixture closes that coverage gap."""
    rec = complete_record(paper_id)
    rec["pnu"]["requires_repair"] = True
    rec["pnu"]["verifier_status"] = "fail"
    rec["pnu"]["verifier_error_count"] = 2
    return rec


def abstract_only_record(paper_id: str = "TEST-ABSTRACT-ONLY") -> dict:
    rec = complete_record(paper_id)
    # No full extraction yet — just metadata + a stub claim from the abstract.
    rec["top_claims"] = [{
        "finding": "Stub abstract-derived claim.",
        "signal": "Abstract-Derived",
        "warrant": "Abstract Statement",
        "credence": 0.5,
        "support_count": 0,
        "attack_count": 0,
        "qualifier": "underspecified",
    }]
    rec["evidence_profile"] = {
        "atlas_credence_mean": None,
        "atlas_credence_percentile": None,
        "paper_claim_count": 0,
        "support_edge_count": 0,
        "attack_edge_count": 0,
        "contradiction_count": 0,
        "search_target_count": 0,
        "dominant_stance": "unknown",
    }
    rec["pnu"] = {}
    return rec


def candidate_pdf_unverified_record(paper_id: str = "TEST-PDF-UNVERIFIED") -> dict:
    rec = abstract_only_record(paper_id)
    rec["top_claims"] = []
    rec["article_meta"]["main_conclusion"] = "Conclusion from candidate PDF."
    return rec


def record_with_long_claim_text(paper_id: str = "TEST-LONG-CLAIM") -> dict:
    rec = complete_record(paper_id)
    rec["top_claims"][0]["finding"] = (
        "This is an intentionally very long claim text that exceeds typical "
        "claim length and is used to verify that canonical-text normalization "
        "and SHA-256 hashing handle long inputs deterministically without "
        "truncation or escaping anomalies. "
    ) * 4
    return rec


def record_with_llm_generated_content(paper_id: str = "TEST-LLM-INJECTED") -> dict:
    """Stage 1 must not produce llm_generated content. To exercise the
    governance check we let the builder run normally and then have the test
    write an llm_generated component row directly into the DB."""
    return complete_record(paper_id)


def all_fixtures() -> dict[str, dict]:
    """Convenience: return all fixtures keyed by paper_id."""
    items = [
        complete_record(),
        partial_record_missing_primary_claim(),
        record_with_attack_count_no_defeaters(),
        record_with_stale_pnu(),
        production_typical_record(),
        abstract_only_record(),
        candidate_pdf_unverified_record(),
        record_with_long_claim_text(),
        record_with_llm_generated_content(),
    ]
    return {rec["paper_id"]: rec for rec in items}
