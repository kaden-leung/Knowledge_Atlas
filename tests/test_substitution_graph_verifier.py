import subprocess
import sys


def test_substitution_graph_verifier_passes():
    result = subprocess.run(
        [sys.executable, "scripts/verify_substitution_graph_contract.py", "--strict"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
