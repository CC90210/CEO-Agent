from __future__ import annotations

import io
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import set_vercel_calendar_env as calendar_env
from lib import secret_loader


def _valid_mapping() -> dict[str, str]:
    return {
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID": "system-client.apps.googleusercontent.com",
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET": "system-client-secret",
        "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN": "system-refresh-token",
        "GOOGLE_SYSTEM_CALENDAR_ADDRESS": "calendar-owner@oasisai.work",
        "GOOGLE_CALENDAR_ID": "primary",
    }


def _legacy_mapping() -> dict[str, str]:
    return {
        "GOOGLE_CLIENT_ID": "generic-client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "generic-client-secret",
        "GWS_CLIENT_ID": "workspace-client.apps.googleusercontent.com",
        "GWS_CLIENT_SECRET": "workspace-client-secret",
        "GOOGLE_REFRESH_TOKEN": "existing-refresh-token",
        "GMAIL_USER": "calendar-owner@oasisai.work",
    }


def test_malformed_unrelated_env_lines_emit_no_warning_or_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    env_path = tmp_path / ".env.agents"
    valid_lines = [f"{name}={value}" for name, value in _valid_mapping().items()]
    env_path.write_text(
        "unrelated malformed line with no equals\n"
        "BROKEN=\"unterminated\n"
        + "\n".join(valid_lines)
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(secret_loader, "ENV_FILE", env_path)
    monkeypatch.setattr(secret_loader, "ACCESS_LOG", tmp_path / "secret_access.log")
    secret_loader.reset_cache()
    monkeypatch.setattr(
        calendar_env,
        "_load_secret_env",
        secret_loader.load_env,
        raising=False,
    )

    # Before the fix, route python-dotenv at the isolated fixture rather than
    # allowing a regression test to read the real credential store.
    dotenv_module = getattr(calendar_env, "dotenv", None)
    if dotenv_module is not None:
        real_dotenv_values = dotenv_module.dotenv_values
        monkeypatch.setattr(
            dotenv_module,
            "dotenv_values",
            lambda _path: real_dotenv_values(env_path),
        )

    try:
        with caplog.at_level(logging.WARNING):
            loaded = calendar_env.load_environment()
    finally:
        secret_loader.reset_cache()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert caplog.records == []
    assert {name: loaded[name] for name in calendar_env.REQUIRED_VARIABLES} == _valid_mapping()


def test_bundle_rejects_generic_google_credentials_as_fallbacks() -> None:
    values = {
        "GOOGLE_CLIENT_ID": "generic-client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "generic-secret",
        "GOOGLE_REFRESH_TOKEN": "generic-refresh-token",
        "GMAIL_USER": "calendar-owner@oasisai.work",
        "GOOGLE_CALENDAR_ID": "primary",
    }

    with pytest.raises(calendar_env.BundleValidationError) as exc_info:
        calendar_env.CalendarCredentialBundle.from_mapping(values)

    message = str(exc_info.value)
    assert "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID" in message
    assert "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET" in message
    assert "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN" in message
    assert "GOOGLE_SYSTEM_CALENDAR_ADDRESS" in message
    assert "generic-refresh-token" not in message


def test_existing_legacy_calendar_values_form_pair_preserving_candidates() -> None:
    candidates = calendar_env.calendar_bundle_candidates(_legacy_mapping())

    assert [source for source, _bundle in candidates] == [
        "GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET + GOOGLE_REFRESH_TOKEN",
        "GWS_CLIENT_ID + GWS_CLIENT_SECRET + GOOGLE_REFRESH_TOKEN",
    ]
    assert [bundle.client_id for _source, bundle in candidates] == [
        "generic-client.apps.googleusercontent.com",
        "workspace-client.apps.googleusercontent.com",
    ]
    assert [bundle.client_secret for _source, bundle in candidates] == [
        "generic-client-secret",
        "workspace-client-secret",
    ]
    assert all(
        bundle.refresh_token == "existing-refresh-token"
        and bundle.address == "calendar-owner@oasisai.work"
        and bundle.calendar_id == "primary"
        for _source, bundle in candidates
    )


def test_apply_verifies_existing_candidates_and_deploys_only_the_accepted_pair(
    tmp_path: Path,
) -> None:
    attempts: list[str] = []
    deployed: list[calendar_env.CalendarCredentialBundle] = []
    output = io.StringIO()

    def verifier(bundle: calendar_env.CalendarCredentialBundle) -> None:
        attempts.append(bundle.client_id)
        if bundle.client_id.startswith("generic-"):
            raise calendar_env.CredentialVerificationError("invalid client/token pair")

    def deployer(
        bundle: calendar_env.CalendarCredentialBundle,
        _app_dir: Path,
    ) -> None:
        deployed.append(bundle)

    result = calendar_env.main(
        ["--apply"],
        env_loader=_legacy_mapping,
        verifier=verifier,
        deployer=deployer,
        app_dir=tmp_path,
        stdout=output,
    )

    assert result == 0
    assert attempts == [
        "generic-client.apps.googleusercontent.com",
        "workspace-client.apps.googleusercontent.com",
    ]
    assert [bundle.client_id for bundle in deployed] == [
        "workspace-client.apps.googleusercontent.com"
    ]
    rendered = output.getvalue()
    for value in _legacy_mapping().values():
        assert value not in rendered


def test_apply_uses_working_encrypted_gws_session_after_stale_env_tokens(
    tmp_path: Path,
) -> None:
    gws_values = {
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID": "live-gws.apps.googleusercontent.com",
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET": "live-gws-secret",
        "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN": "live-gws-refresh",
        "GOOGLE_SYSTEM_CALENDAR_ADDRESS": "calendar-owner@oasisai.work",
        "GOOGLE_CALENDAR_ID": "primary",
    }
    gws_bundle = calendar_env.CalendarCredentialBundle.from_mapping(gws_values)
    attempts: list[str] = []
    deployed: list[calendar_env.CalendarCredentialBundle] = []
    output = io.StringIO()

    def verifier(bundle: calendar_env.CalendarCredentialBundle) -> None:
        attempts.append(bundle.client_id)
        if bundle is not gws_bundle:
            raise calendar_env.CredentialVerificationError("invalid_grant")

    result = calendar_env.main(
        ["--apply"],
        env_loader=_legacy_mapping,
        verifier=verifier,
        deployer=lambda bundle, _app_dir: deployed.append(bundle),
        gws_loader=lambda _values: ("encrypted gws credential store", gws_bundle),
        app_dir=tmp_path,
        stdout=output,
    )

    assert result == 0
    assert attempts[-1] == "live-gws.apps.googleusercontent.com"
    assert deployed == [gws_bundle]
    rendered = output.getvalue()
    assert "encrypted gws credential store" in rendered
    for value in gws_values.values():
        assert value not in rendered


def test_store_flag_persists_the_verified_bundle_to_the_env_store(tmp_path: Path) -> None:
    # 2026-09-24: the fix reached Vercel only; production is the Cloudflare
    # Worker, whose secrets come FROM the env store, so booking stayed down.
    gws_bundle = calendar_env.CalendarCredentialBundle.from_mapping({
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID": "live-gws.apps.googleusercontent.com",
        "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET": "live-gws-secret",
        "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN": "live-gws-refresh",
        "GOOGLE_SYSTEM_CALENDAR_ADDRESS": "calendar-owner@oasisai.work",
        "GOOGLE_CALENDAR_ID": "primary",
    })
    env_file = tmp_path / ".env.agents"
    env_file.write_text("UNRELATED_KEY=keep-me\nGOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN=stale\n", encoding="utf-8")
    output = io.StringIO()

    result = calendar_env.main(
        ["--apply", "--store"],
        env_loader=_legacy_mapping,
        verifier=lambda bundle: None if bundle is gws_bundle else (_ for _ in ()).throw(
            calendar_env.CredentialVerificationError("invalid_grant")),
        deployer=lambda _bundle, _app_dir: None,
        gws_loader=lambda _values: ("encrypted gws credential store", gws_bundle),
        app_dir=tmp_path,
        stdout=output,
        storer=lambda bundle: calendar_env.store_bundle(bundle, env_file),
    )

    assert result == 0
    stored = env_file.read_text(encoding="utf-8")
    assert "UNRELATED_KEY=keep-me" in stored, "peer keys must survive"
    assert "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN=live-gws-refresh" in stored
    assert "=stale" not in stored
    assert "live-gws" not in output.getvalue(), "values never reach the output"
    assert "secrets-push --app oasis-command-center" in output.getvalue()


def test_gws_export_is_captured_unmasked_without_secret_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exported = {
        "type": "authorized_user",
        "client_id": "live-gws.apps.googleusercontent.com",
        "client_secret": "live-gws-secret",
        "refresh_token": "live-gws-refresh",
    }
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=__import__("json").dumps(exported), stderr="")

    source, bundle = calendar_env.export_gws_calendar_bundle(
        {"GMAIL_USER": "calendar-owner@oasisai.work"},
        runner=runner,
        find_executable=lambda _name: "C:/tools/gws.CMD",
    )

    assert source == "encrypted gws credential store"
    assert bundle.client_id == exported["client_id"]
    assert calls[0][0] == ["C:/tools/gws.CMD", "auth", "export", "--unmasked"]
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["shell"] is False
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize("missing_name", calendar_env.REQUIRED_VARIABLES)
def test_bundle_requires_every_system_calendar_field(missing_name: str) -> None:
    values = _valid_mapping()
    del values[missing_name]

    with pytest.raises(calendar_env.BundleValidationError, match=missing_name):
        calendar_env.CalendarCredentialBundle.from_mapping(values)


def test_default_mode_is_dry_run_and_never_calls_google_or_vercel(tmp_path: Path) -> None:
    calls: list[str] = []
    output = io.StringIO()

    def verifier(_bundle: calendar_env.CalendarCredentialBundle) -> None:
        calls.append("google")

    def deployer(
        _bundle: calendar_env.CalendarCredentialBundle,
        _app_dir: Path,
    ) -> None:
        calls.append("vercel")

    result = calendar_env.main(
        [],
        env_loader=_valid_mapping,
        verifier=verifier,
        deployer=deployer,
        app_dir=tmp_path,
        stdout=output,
    )

    assert result == 0
    assert calls == []
    assert "DRY RUN" in output.getvalue()
    assert "--apply" in output.getvalue()


def test_cli_output_never_contains_credential_values(tmp_path: Path) -> None:
    values = _valid_mapping()
    output = io.StringIO()

    result = calendar_env.main(
        [],
        env_loader=lambda: values,
        app_dir=tmp_path,
        stdout=output,
    )

    assert result == 0
    rendered = output.getvalue()
    for value in values.values():
        assert value not in rendered
    for name in calendar_env.REQUIRED_VARIABLES:
        assert name in rendered


def test_apply_verifies_complete_bundle_before_deploying(tmp_path: Path) -> None:
    events: list[object] = []

    def verifier(bundle: calendar_env.CalendarCredentialBundle) -> None:
        events.append(("verify", bundle))

    def deployer(bundle: calendar_env.CalendarCredentialBundle, app_dir: Path) -> None:
        events.append(("deploy", bundle, app_dir))

    result = calendar_env.main(
        ["--apply"],
        env_loader=_valid_mapping,
        verifier=verifier,
        deployer=deployer,
        app_dir=tmp_path,
        stdout=io.StringIO(),
    )

    assert result == 0
    assert [event[0] for event in events] == ["verify", "deploy"]
    assert events[0][1] is events[1][1]


def test_failed_same_client_verification_prevents_any_deploy(tmp_path: Path) -> None:
    deployed = False

    def verifier(_bundle: calendar_env.CalendarCredentialBundle) -> None:
        raise calendar_env.CredentialVerificationError("OAuth client/token mismatch")

    def deployer(
        _bundle: calendar_env.CalendarCredentialBundle,
        _app_dir: Path,
    ) -> None:
        nonlocal deployed
        deployed = True

    output = io.StringIO()
    result = calendar_env.main(
        ["--apply"],
        env_loader=_valid_mapping,
        verifier=verifier,
        deployer=deployer,
        gws_loader=lambda _values: None,
        app_dir=tmp_path,
        stdout=output,
    )

    assert result == 1
    assert deployed is False
    assert "OAuth client/token mismatch" in output.getvalue()


def test_google_verification_requires_calendar_scope_and_owner_identity() -> None:
    bundle = calendar_env.CalendarCredentialBundle.from_mapping(_valid_mapping())

    with pytest.raises(calendar_env.CredentialVerificationError, match="Calendar scope"):
        calendar_env.verify_google_bundle(
            bundle,
            exchange_token=lambda *_args: {
                "access_token": "temporary-access-token",
                "scope": "openid email",
            },
            fetch_calendar=lambda *_args: {"id": "calendar-owner@oasisai.work"},
        )

    with pytest.raises(calendar_env.CredentialVerificationError, match="owner"):
        calendar_env.verify_google_bundle(
            bundle,
            exchange_token=lambda *_args: {
                "access_token": "temporary-access-token",
                "scope": "https://www.googleapis.com/auth/calendar.events",
            },
            fetch_calendar=lambda *_args: {"id": "different-owner@oasisai.work"},
        )


def test_deployer_sets_exact_production_bundle_without_shell_or_output(tmp_path: Path) -> None:
    bundle = calendar_env.CalendarCredentialBundle.from_mapping(_valid_mapping())
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    calendar_env.deploy_bundle(
        bundle,
        tmp_path,
        runner=runner,
        find_executable=lambda _name: "C:/tools/vercel.CMD",
    )

    assert [command[3] for command, _kwargs in calls] == list(calendar_env.REQUIRED_VARIABLES)
    assert all(
        command[:3] == ["C:/tools/vercel.CMD", "env", "add"]
        for command, _kwargs in calls
    )
    assert all(
        command[4:] == ["production", "--force", "--sensitive", "--yes"]
        for command, _kwargs in calls
    )
    assert all(kwargs["shell"] is False for _command, kwargs in calls)
    assert all(
        "--use-system-ca" in str(kwargs["env"]["NODE_OPTIONS"]).split()
        for _command, kwargs in calls
    )
    assert [kwargs["input"].rstrip("\n") for _command, kwargs in calls] == [
        value for _name, value in bundle.vercel_items()
    ]


def test_deployer_preserves_existing_node_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = calendar_env.CalendarCredentialBundle.from_mapping(_valid_mapping())
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096 --use-system-ca")

    def runner(_command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    calendar_env.deploy_bundle(
        bundle,
        tmp_path,
        runner=runner,
        find_executable=lambda _name: "C:/tools/vercel.CMD",
    )

    assert calls[0]["env"]["NODE_OPTIONS"] == "--max-old-space-size=4096 --use-system-ca"


def test_deployer_fails_closed_when_vercel_cli_is_not_installed(tmp_path: Path) -> None:
    bundle = calendar_env.CalendarCredentialBundle.from_mapping(_valid_mapping())

    with pytest.raises(calendar_env.DeploymentError, match="Vercel CLI"):
        calendar_env.deploy_bundle(
            bundle,
            tmp_path,
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not be called"),
            find_executable=lambda _name: None,
        )
