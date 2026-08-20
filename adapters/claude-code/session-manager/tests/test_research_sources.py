import json

import research_sources


def test_list_sources_empty(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    assert research_sources.list_sources() == []


def test_add_source_persists(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    source = research_sources.add_source("https://example.com/feed", "Example Feed")
    assert source["url"] == "https://example.com/feed"
    assert source["label"] == "Example Feed"
    assert source["blacklisted"] is False
    assert "id" in source
    on_disk = json.loads(fake_file.read_text())
    assert len(on_disk["sources"]) == 1


def test_add_source_duplicate_returns_none(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    research_sources.add_source("https://example.com/feed", "Example Feed")
    result = research_sources.add_source("https://example.com/feed", "Duplicate Attempt")
    assert result is None


def test_find_source_by_id(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    added = research_sources.add_source("https://example.com/feed", "Example Feed")
    found = research_sources.find_source(added["id"])
    assert found["url"] == "https://example.com/feed"


def test_find_source_unknown_returns_none(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    assert research_sources.find_source("nonexistent-id") is None


def test_set_blacklisted_toggles(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    added = research_sources.add_source("https://example.com/feed", "Example Feed")
    updated = research_sources.set_blacklisted(added["id"], True)
    assert updated["blacklisted"] is True
