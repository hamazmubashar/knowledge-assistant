import hashlib
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_acceptance.py"
spec = importlib.util.spec_from_file_location("verify_acceptance", SCRIPT)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

SECRET = b"id,question\nq01,SECRET QUESTION TEXT\n"


def make(tmp_path, sha_text):
    data, sha = tmp_path / "set.csv", tmp_path / "set.sha256"
    data.write_bytes(SECRET)
    sha.write_text(sha_text)
    return ["verify", str(data), str(sha)]


def test_match_returns_zero_and_never_prints_contents(tmp_path, capsys):
    good = hashlib.sha256(SECRET).hexdigest()
    assert verify.main(make(tmp_path, f"{good}  acceptance_v1.csv\n")) == 0
    out = capsys.readouterr().out
    assert "RESULT: MATCH" in out and "SECRET" not in out and "q01" not in out


def test_mismatch_returns_two(tmp_path, capsys):
    assert verify.main(make(tmp_path, "0" * 64)) == 2
    out = capsys.readouterr().out
    assert "MISMATCH" in out and "SECRET" not in out


def test_missing_or_malformed_fingerprint_returns_three(tmp_path):
    assert verify.main(make(tmp_path, "not a hash")) == 3
    assert verify.main(["verify", str(tmp_path / "nope.csv"), str(tmp_path / "nope.sha")]) == 3
