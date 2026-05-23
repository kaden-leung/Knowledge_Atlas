import json
import subprocess
import sys


def test_substitution_admit_index_builder_writes_compact_payload(tmp_path):
    output = tmp_path / "substitution_admit_index.json"
    result = subprocess.run(
        [sys.executable, "scripts/build_substitution_admit_index.py", "--output", str(output), "--limit", "5"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text())
    assert payload["schema_version"] == "ka_substitution_admit_index_v1"
    assert payload["source"]["llm_used"] is False
    assert payload["summary"]["paper_count"] == 5
    assert payload["summary"]["dv_count"] > 0
    assert payload["papers"][0]["paper_lookup"]["status"] == "loaded_from_article_details"
