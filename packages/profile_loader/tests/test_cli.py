import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ACUVIM_L_PATH = REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "profile_loader", *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_validate_succeeds_on_committed_profile():
    result = _run("validate", str(ACUVIM_L_PATH))
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout
    assert "Acuvim L" in result.stdout


def test_validate_fails_on_broken_profile(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not a profile", encoding="utf-8")
    result = _run("validate", str(bad))
    assert result.returncode != 0
    assert result.stderr


def test_help_lists_validate_subcommand():
    result = _run("--help")
    assert result.returncode == 0
    assert "validate" in result.stdout
