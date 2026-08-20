import json

from app.services import eval_results


def test_read_last_run_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: tmp_path / "last_run.json")
    assert eval_results.read_last_run() is None


def test_read_last_run_parses_results(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [
            {"id": "case_a", "name": "Case A", "score": 9.2, "reasoning": "Good."},
            {"id": "case_b", "name": "Case B", "score": 3.0, "reasoning": "Weak."},
        ],
    }))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    data = eval_results.read_last_run()
    assert data["timestamp"] == "2026-07-21T13:49:31"
    assert len(data["results"]) == 2


def test_read_last_run_annotates_baseline_delta(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    baselines = tmp_path / "baselines.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [{"id": "case_a", "name": "Case A", "score": 9.2, "reasoning": "Good."}],
    }))
    baselines.write_text(json.dumps({"case_a": {"score": 8.0, "model": "x", "date": "2026-05-13"}}))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    monkeypatch.setattr(eval_results, "_baselines_path", lambda: baselines)
    data = eval_results.read_last_run()
    case = next(r for r in data["results"] if r["id"] == "case_a")
    assert case["baseline_score"] == 8.0
    assert round(case["delta"], 1) == 1.2


def test_read_last_run_missing_baseline_has_null_delta(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    baselines = tmp_path / "baselines.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [{"id": "new_case", "name": "New Case", "score": 5.0, "reasoning": "N/A"}],
    }))
    baselines.write_text(json.dumps({}))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    monkeypatch.setattr(eval_results, "_baselines_path", lambda: baselines)
    data = eval_results.read_last_run()
    case = data["results"][0]
    assert case["baseline_score"] is None
    assert case["delta"] is None
