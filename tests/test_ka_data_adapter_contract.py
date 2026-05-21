from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "ka_data_adapter.js"


def test_data_adapter_knows_soft_rebuild_payload_names():
    source = ADAPTER_PATH.read_text()
    assert "paper_pnus: 'data/ka_payloads/paper_pnus.json'" in source
    assert "topic_voi: 'data/ka_payloads/topic_voi.json'" in source
    assert "theories: 'data/ka_payloads/theories.json'" in source
    assert "mechanisms: 'data/ka_payloads/mechanisms.json'" in source
