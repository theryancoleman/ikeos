import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import pane_parser


def test_parse_remote_control_enabled():
    pane = "some output\nRemote control enabled\n"
    assert pane_parser.parse_remote_control_state(pane) == "enabled"


def test_parse_remote_control_disabled():
    pane = "some output\nRemote control disabled\n"
    assert pane_parser.parse_remote_control_state(pane) == "disabled"


def test_parse_remote_control_none_when_absent():
    pane = "some output\nno mention here\n"
    assert pane_parser.parse_remote_control_state(pane) is None


def test_parse_remote_control_returns_last_state():
    pane = "Remote control enabled\nRemote control disabled\n"
    assert pane_parser.parse_remote_control_state(pane) == "disabled"


def test_parse_remote_control_state_from_url():
    pane = "This session is available at https://claude.ai/code/session_abc123\n"
    assert pane_parser.parse_remote_control_state(pane) == "enabled"


def test_parse_rc_dialog_open_true():
    pane = (
        "Remote Control\n"
        "  This session is available at https://claude.ai/code/session_abc123\n"
        "  ❯ Continue\n"
        "  Enter to select · Esc to continue\n"
    )
    assert pane_parser.parse_rc_dialog_open(pane) is True


def test_parse_rc_dialog_open_false_no_url():
    pane = "Enter to select · Esc to continue\n"
    assert pane_parser.parse_rc_dialog_open(pane) is False


def test_parse_rc_dialog_open_false_after_dismiss():
    pane = "Remote control enabled\n> \n"
    assert pane_parser.parse_rc_dialog_open(pane) is False


def test_parse_message_count_counts_prompt_lines():
    pane = "hello\n> \nresponse\n> \nresponse2\n"
    assert pane_parser.parse_message_count(pane) == 2


def test_parse_message_count_zero_when_none():
    pane = "no prompts here\n"
    assert pane_parser.parse_message_count(pane) == 0


def test_parse_compaction_detected_true():
    pane = "Your context has been compacted to save space.\n"
    assert pane_parser.parse_compaction_detected(pane) is True


def test_parse_compaction_detected_context_window():
    pane = "Context window is nearly full.\n"
    assert pane_parser.parse_compaction_detected(pane) is True


def test_parse_compaction_detected_false():
    pane = "Normal output here.\n"
    assert pane_parser.parse_compaction_detected(pane) is False


def test_parse_activity_thinking_spinner():
    pane = "✻ Razzmatazzing… (2m 26s · ↓ 9.0k tokens · almost done thinking)\n"
    assert pane_parser.parse_activity(pane) == "thinking"


def test_parse_activity_thinking_keyword():
    pane = "some output\nalmost done thinking\n"
    assert pane_parser.parse_activity(pane) == "thinking"


def test_parse_activity_tool_waiting():
    pane = "● Bash(ls /tmp)\n  ⎿  Waiting…\n"
    assert pane_parser.parse_activity(pane) == "working"


def test_parse_activity_subagent_running():
    pane = "● main\n◯ implementer  Task 2: something                     50s\n"
    assert pane_parser.parse_activity(pane) == "working"


def test_parse_activity_token_stream():
    pane = "normal output\n\n· doing stuff… (↓ 4.2k tokens)\n❯ \n"
    assert pane_parser.parse_activity(pane) == "working"


def test_parse_activity_idle():
    pane = "Previous response here.\n❯ \n"
    assert pane_parser.parse_activity(pane) == "idle"


def test_parse_activity_completion_stat_is_idle():
    pane = "✻ Brewed for 21s\n❯ \n"
    assert pane_parser.parse_activity(pane) == "idle"


def _make_session(age_hours=0, messages=0, compaction=False):
    started = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "started_at": started,
        "message_count": messages,
        "compaction_detected": compaction,
    }


def test_compute_health_fresh():
    assert pane_parser.compute_health(_make_session(0.5, 10)) == "fresh"


def test_compute_health_aging_by_time():
    assert pane_parser.compute_health(_make_session(2, 5)) == "aging"


def test_compute_health_aging_by_messages():
    assert pane_parser.compute_health(_make_session(0.5, 30)) == "aging"


def test_compute_health_aging_by_compaction():
    assert pane_parser.compute_health(_make_session(0.5, 5, compaction=True)) == "aging"


def test_compute_health_heavy_by_time():
    assert pane_parser.compute_health(_make_session(4, 5)) == "heavy"


def test_compute_health_heavy_by_messages():
    assert pane_parser.compute_health(_make_session(0.5, 60)) == "heavy"


def test_parse_token_usage_tokens_remaining():
    pane = "some output\n110k tokens remaining\n> \n"
    result = pane_parser.parse_token_usage(pane)
    assert result["tokens_remaining"] == "110k"
    assert result["context_pct"] is None


def test_parse_token_usage_context_pct():
    pane = "some output\nContext: 45%\n> \n"
    result = pane_parser.parse_token_usage(pane)
    assert result["context_pct"] == 45
    assert result["tokens_remaining"] is None


def test_parse_token_usage_both():
    pane = "context window 55%\n90k tokens remaining\n"
    result = pane_parser.parse_token_usage(pane)
    assert result["context_pct"] == 55
    assert result["tokens_remaining"] == "90k"


def test_parse_token_usage_none_when_absent():
    pane = "Normal response here.\n> \n"
    result = pane_parser.parse_token_usage(pane)
    assert result["tokens_remaining"] is None
    assert result["context_pct"] is None


def test_parse_token_usage_handles_thousands():
    pane = "110,000 tokens remaining\n"
    result = pane_parser.parse_token_usage(pane)
    assert result["tokens_remaining"] == "110,000"
