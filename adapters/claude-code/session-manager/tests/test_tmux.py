import shlex
import subprocess
import pytest
from unittest.mock import patch, call, MagicMock

import tmux


def test_has_session_returns_true_when_exists(mocker):
    mocker.patch("subprocess.run", return_value=MagicMock(returncode=0))
    assert tmux.has_session("my-session") is True


def test_has_session_returns_false_when_missing(mocker):
    mocker.patch("subprocess.run", return_value=MagicMock(returncode=1))
    assert tmux.has_session("my-session") is False


def test_launch_session_runs_correct_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    tmux.launch_session("my-session", "/home/user/projects/foo")
    expected = ["tmux", "new-session", "-d", "-s", "my-session",
                "-c", "/home/user/projects/foo",
                "bash", "-lc", shlex.join(tmux.CLAUDE_CMD)]
    mock_run.assert_called_once_with(expected, check=True)


def test_kill_session_runs_correct_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    tmux.kill_session("my-session")
    mock_run.assert_called_once_with(
        ["tmux", "kill-session", "-t", "my-session"],
        check=True
    )


def test_send_command_runs_correct_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    tmux.send_command("my-session", "/clear")
    mock_run.assert_called_once_with(
        ["tmux", "send-keys", "-t", "my-session", "/clear", "Enter"],
        check=True
    )


def test_send_enter_runs_correct_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    tmux.send_enter("my-session")
    mock_run.assert_called_once_with(
        ["tmux", "send-keys", "-t", "my-session", "Enter"],
        check=True
    )


def test_capture_pane_returns_output(mocker):
    mocker.patch("subprocess.run", return_value=MagicMock(
        returncode=0, stdout="some pane output\n> \n"
    ))
    result = tmux.capture_pane("my-session")
    assert result == "some pane output\n> \n"


def test_wait_until_idle_returns_true_when_idle(mocker):
    mocker.patch("tmux.time.sleep")
    mocker.patch("tmux.time.monotonic", side_effect=[0.0, 5.0])
    mocker.patch("tmux.has_session", return_value=True)
    mocker.patch("tmux.capture_pane", return_value="pane output")
    mocker.patch("tmux.parse_activity", return_value="idle")
    assert tmux.wait_until_idle("s", timeout=10.0) is True


def test_wait_until_idle_returns_false_when_session_gone(mocker):
    mocker.patch("tmux.time.sleep")
    mocker.patch("tmux.time.monotonic", side_effect=[0.0, 5.0])
    mocker.patch("tmux.has_session", return_value=False)
    mocker.patch("tmux.capture_pane", return_value="")
    assert tmux.wait_until_idle("s", timeout=10.0) is False


def test_wait_until_idle_returns_false_on_timeout(mocker):
    mocker.patch("tmux.time.sleep")
    # deadline = time.monotonic() + timeout → call 1 returns 0.0, deadline=10
    # In loop: parse_activity returns "working" (not idle), then time.monotonic() → call 2 returns 15 ≥ 10 → False
    mocker.patch("tmux.time.monotonic", side_effect=[0.0, 15.0])
    mocker.patch("tmux.has_session", return_value=True)
    mocker.patch("tmux.capture_pane", return_value="pane")
    mocker.patch("tmux.parse_activity", return_value="working")
    assert tmux.wait_until_idle("s", timeout=10.0) is False


def test_send_prompt_sends_escape_then_command_when_idle(mocker):
    mocker.patch("tmux.wait_until_idle", return_value=True)
    mock_key = mocker.patch("tmux.send_key")
    mock_cmd = mocker.patch("tmux.send_command")
    mocker.patch("tmux.time.sleep")
    assert tmux.send_prompt("s", "/triage") is True
    mock_key.assert_called_once_with("s", "Escape")
    mock_cmd.assert_called_once_with("s", "/triage")


def test_send_prompt_returns_false_on_timeout(mocker):
    mocker.patch("tmux.wait_until_idle", return_value=False)
    assert tmux.send_prompt("s", "/triage") is False


def test_list_session_names_returns_set(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    mock_run.return_value = mocker.Mock(returncode=0, stdout="alpha\nbeta\n")
    assert tmux.list_session_names() == {"alpha", "beta"}


def test_list_session_names_returns_empty_set_when_no_server(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    mock_run.return_value = mocker.Mock(returncode=1, stdout="")
    assert tmux.list_session_names() == set()


def test_launch_session_overrides_model_when_given(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    tmux.launch_session("my-session", "/home/user/projects/foo", model="claude-opus-4-8")
    args = mock_run.call_args[0][0]
    cmd_str = args[-1]
    assert "--model claude-opus-4-8" in cmd_str


def test_wait_until_idle_requires_consecutive_idle_readings(mocker):
    mocker.patch("tmux.has_session", return_value=True)
    mocker.patch("tmux.capture_pane", return_value="pane text")
    parse_mock = mocker.patch("tmux.parse_activity", side_effect=["idle", "working", "idle", "idle"])
    mocker.patch("tmux.time.sleep")
    result = tmux.wait_until_idle("s", timeout=60, poll_interval=0, required_consecutive=2)
    assert result is True
    assert parse_mock.call_count == 4
