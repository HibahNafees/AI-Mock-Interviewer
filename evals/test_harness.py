"""The harness runs end to end with Fire mocked (free); run from backend/:
.venv/bin/python -m pytest ../evals"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run as cli  # noqa: E402
from harness import Run, checks  # noqa: E402


def test_mock_run_completes_interviews_and_reports(tmp_path, capsys):
    cli.main(["--mock", "--fields", "backend", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "backend/strong" in out and "backend/rambling" in out
    assert "ERROR" not in out
    assert "report ready" not in out  # status lives in the saved JSON
    saved = list(tmp_path.glob("eval-*.json"))
    assert len(saved) == 1
    import json

    data = json.loads(saved[0].read_text())
    for r in data["runs"]:
        assert r["status"] == "report ready", r
        assert r["turns"] >= 2 and r["question_scores"]


def test_checks_flag_a_weak_answer_scoring_above_a_strong_one():
    runs = [
        Run("backend", "strong", overall=2.5, verdict="no hire"),
        Run("backend", "weak", overall=3.0, verdict="hire"),
    ]
    failed = [name for name, ok in checks(runs) if not ok]
    assert any("strong (2.5) scores above weak" in n for n in failed)
    assert any("weak: verdict is not hire" in n for n in failed)
    assert any("strong: verdict is not no hire" in n for n in failed)
