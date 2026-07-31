"""Runtime enforcement for capability-declared bridge argument policy."""

from bravo_cli import bridge_chat_server as bridge


_script_argument_violation = bridge._script_argument_violation
_script_confirmation_argument = bridge._script_confirmation_argument


def test_denied_argument_cannot_bypass_confirmation_gate():
    spec = {"deny_args": ["--rewrite", "--strings"], "mutating": False}
    assert _script_argument_violation(spec, ["repo", "--rewrite"]) == "--rewrite"
    assert _script_argument_violation(spec, ["repo", "--rewrite=true"]) == "--rewrite"
    assert _script_argument_violation(spec, ["repo", "--rew"]) == "--rewrite"
    assert _script_argument_violation(spec, ["repo", "--str", "outside.txt"]) == "--strings"


def test_unrelated_scanner_arguments_remain_allowed():
    spec = {"deny_args": ["--rewrite"], "mutating": False}
    assert _script_argument_violation(spec, ["repo", "--emails-heuristic"]) is None


def test_argument_based_mutation_escalation_handles_argparse_abbreviations():
    spec = {"confirm_args": ["--screenshot"], "mutating": False}
    assert _script_confirmation_argument(spec, ["https://example.com"]) is None
    assert _script_confirmation_argument(spec, ["--screenshot", "out.png"]) == "--screenshot"
    assert _script_confirmation_argument(spec, ["--screenshot=out.png"]) == "--screenshot"
    assert _script_confirmation_argument(spec, ["--screen", "out.png"]) == "--screenshot"


def test_fixed_arguments_precede_model_supplied_arguments():
    spec = {"subcmd": "scan", "fixed_args": ["."]}
    assert bridge._script_runtime_args(spec, ["--emails-heuristic"]) == [
        "scan",
        ".",
        "--emails-heuristic",
    ]


def test_safe_run_script_rejects_denied_arg_before_process_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bridge,
        "SCRIPT_ALLOWLIST",
        {
            "pii_scan": {
                "path": "scripts/pii_sweep.py",
                "subcmd": None,
                "mutating": False,
                "deny_args": ["--rewrite"],
            }
        },
    )
    output, is_error = bridge._ChatHandler._safe_run_script(
        None,
        tmp_path,
        "pii_scan",
        ["repo", "--rew"],
        confirm=True,
    )
    assert is_error is True
    assert "argument_not_allowed" in output


def test_safe_run_script_requires_confirmation_for_sensitive_extra_arg(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bridge,
        "SCRIPT_ALLOWLIST",
        {
            "page_scrape": {
                "path": "scripts/browser/cloak_browser_tool.py",
                "subcmd": "scrape",
                "mutating": False,
                "confirm_args": ["--screenshot"],
            }
        },
    )
    output, is_error = bridge._ChatHandler._safe_run_script(
        None,
        tmp_path,
        "page_scrape",
        ["https://example.com", "--screen", "out.png"],
        confirm=False,
    )
    assert is_error is True
    assert "confirm_required" in output
    assert "--screenshot" in output
