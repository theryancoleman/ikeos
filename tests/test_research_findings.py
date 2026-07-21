import json
import pytest
from unittest.mock import patch
from app.services import research_findings as rf


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "library").mkdir()
    return tmp_path


def test_get_research_findings_none_when_env_not_set():
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", ""):
        assert rf.get_research_findings() is None


def test_get_research_findings_none_when_file_missing(config_dir):
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None


def test_get_research_findings_reads_file(config_dir):
    data = {
        "generated_at": "2026-07-16T14:00:00Z",
        "summaries": [
            {"url": "https://example.com", "label": "Example", "key_points": ["a"], "notable_updates": ["b"]}
        ],
    }
    (config_dir / "library" / "research-summaries-latest.json").write_text(json.dumps(data), encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        result = rf.get_research_findings()
    assert result["generated_at"] == "2026-07-16T14:00:00Z"
    assert len(result["summaries"]) == 1
    assert result["summaries"][0]["label"] == "Example"


def test_get_research_findings_none_on_malformed_json(config_dir):
    (config_dir / "library" / "research-summaries-latest.json").write_text("{not valid json", encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None


def test_get_research_findings_none_when_root_not_dict(config_dir):
    (config_dir / "library" / "research-summaries-latest.json").write_text("[1, 2, 3]", encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None
