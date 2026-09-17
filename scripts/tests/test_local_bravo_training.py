from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dataset_builder = _load_module("train_local_bravo", "scripts/train_local_bravo.py")
trainer = _load_module("run_qlora_train", "scripts/run_qlora_train.py")


def test_repo_mining_builds_chatml_with_required_coverage() -> None:
    samples = dataset_builder.build_samples(REPO_ROOT)
    records = [sample.to_record() for sample in samples]

    assert len(records) >= 150
    assert len({record["messages"][1]["content"] for record in records}) == len(records)
    assert all(
        [message["role"] for message in record["messages"]]
        == ["system", "user", "assistant"]
        for record in records
    )
    assert all(
        record["messages"][0]["content"] == dataset_builder.BRAVO_SYSTEM_PROMPT
        for record in records
    )

    sources = {sample.source for sample in samples}
    assert "scripts/integrations/send_gateway.py" in sources
    assert "scripts/integrations/stripe_tool.py" in sources
    assert "scripts/integrations/turso_tool.py" in sources
    assert "skills/send-gateway/SKILL.md" in sources
    assert "skills/auto-generated/score-b2b-lead-quality/SKILL.md" in sources
    assert "brain/SOUL.md" in sources
    assert "AGENTS.md" in sources
    assert "scripts/llm_training/generate_dataset.py" not in sources
    assert "scripts/llm_training/train_unsloth.py" not in sources

    soul_prompts = [
        sample.user.lower() for sample in samples if sample.source == "brain/SOUL.md"
    ]
    assert any("personality" in prompt for prompt in soul_prompts)

    send_gateway = next(
        sample
        for sample in samples
        if sample.source == "scripts/integrations/send_gateway.py"
    )
    assert "- `Bravo performs on behalf" not in send_gateway.assistant


def test_backend_seed_examples_are_complete_and_parseable() -> None:
    samples = [
        sample
        for sample in dataset_builder.build_samples(REPO_ROOT)
        if sample.kind == "backend_code"
    ]
    combined = "\n".join(sample.assistant for sample in samples)

    for required_fragment in (
        "socket.gethostbyname",
        "X-Forwarded-For",
        "request.remote_addr",
        "time.monotonic",
        "hmac.compare_digest",
        "jwt.decode",
        "sqlite3.connect",
    ):
        assert required_fragment in combined

    python_blocks = []
    for sample in samples:
        python_blocks.extend(
            re.findall(r"```python\n(.*?)```", sample.assistant, flags=re.DOTALL)
        )
    assert len(python_blocks) >= 7
    for block in python_blocks:
        ast.parse(block)
        assert "TODO" not in block
        assert "pass  #" not in block

    assert "```typescript" in combined
    assert "crypto.createHmac" in combined


def test_curated_corpus_includes_direct_execution_without_disclaimer_bloat() -> None:
    samples = dataset_builder.build_samples(REPO_ROOT)
    direct = [sample for sample in samples if sample.kind == "direct_execution"]

    assert direct
    assert any("without generic disclaimer" in sample.user.lower() for sample in direct)
    assert all("as an ai" not in sample.assistant.lower() for sample in direct)


def test_live_verifier_accepts_the_curated_reference_answers() -> None:
    samples = dataset_builder.build_samples(REPO_ROOT)
    dns = next(
        sample
        for sample in samples
        if "one IPv4 address" in sample.user
    )
    visitor = next(
        sample
        for sample in samples
        if sample.user.startswith("Build a Flask endpoint")
    )
    identity = next(sample for sample in samples if sample.kind == "identity")

    assert trainer.response_passes("dns", dns.assistant)
    assert trainer.response_passes("visitor_ip", visitor.assistant)
    assert trainer.response_passes("identity", identity.assistant)


def test_sanitizer_removes_credentials_pii_and_machine_paths() -> None:
    unsafe = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n"
        "owner@example-business.ca id=123e4567-e89b-12d3-a456-426614174000\n"
        "C:\\Users\\Alice\\private\\file.txt\n"
        "-----BEGIN " + "PRIVATE KEY-----\nsecret\n-----END " + "PRIVATE KEY-----"
    )
    safe = dataset_builder.sanitize_text(unsafe)

    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in safe
    assert "owner@example-business.ca" not in safe
    assert "123e4567-e89b-12d3-a456-426614174000" not in safe
    assert "C:\\Users\\Alice" not in safe
    assert "\nsecret\n" not in safe
    assert "<REDACTED" in safe or "<REPO_PATH>" in safe


def test_sanitizer_covers_canonical_provider_secrets_phones_and_public_ips() -> None:
    discord = "M" + "A" * 23 + "." + "B" * 6 + "." + "C" * 27
    meta_eaa = "EAA" + "D" * 100
    meta_pair = "1" * 15 + "|" + "E" * 25
    env_fallback = 'os.getenv("API_SECRET", "' + "F" * 16 + '")'
    pgp = (
        "-----BEGIN "
        + "PGP PRIVATE KEY BLOCK-----\nsecret\n-----END "
        + "PGP PRIVATE KEY BLOCK-----"
    )
    values = [
        "sk_" + "live_" + "A" * 24,
        "rk_" + "live_" + "B" * 24,
        "AKIA" + "C" * 16,
        "AIza" + "G" * 35,
        "123456:" + "H" * 35,
        "I" * 32,
        "+1 (514) 555-0199",
        "8.8.8.8",
        discord,
        meta_eaa,
        meta_pair,
        env_fallback,
        pgp,
    ]
    unsafe = "\n".join(
        [
            *values[:5],
            f'api_key = "{values[5]}"',
            *values[6:],
        ]
    )

    safe = dataset_builder.sanitize_text(unsafe)

    for value in values:
        assert value not in safe
    assert "<REDACTED_SECRET>" in safe
    assert "<REDACTED_PHONE>" in safe
    assert "<REDACTED_IP>" in safe


def test_dataset_output_is_deterministic_and_strictly_valid(tmp_path: Path) -> None:
    samples = dataset_builder.build_samples(REPO_ROOT)
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"

    first_stats = dataset_builder.write_dataset(samples, first, repo_root=REPO_ROOT)
    second_stats = dataset_builder.write_dataset(samples, second, repo_root=REPO_ROOT)

    assert first.read_bytes() == second.read_bytes()
    assert first_stats["sha256"] == second_stats["sha256"]
    assert first_stats["samples"] == len(samples)
    verified = dataset_builder.verify_dataset(first)
    assert verified["samples"] == len(samples)
    assert first.with_suffix(".manifest.json").is_file()


def test_dataset_verifier_rejects_missing_system_and_duplicates(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    row = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
    }
    invalid.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(dataset_builder.DatasetValidationError):
        dataset_builder.verify_dataset(invalid)


def test_dataset_verifier_rejects_content_that_no_longer_matches_manifest(
    tmp_path: Path,
) -> None:
    output = tmp_path / "dataset.jsonl"
    dataset_builder.write_dataset(
        dataset_builder.build_samples(REPO_ROOT), output, repo_root=REPO_ROOT
    )
    output.write_text(
        output.read_text(encoding="utf-8").replace("Flask", "FlaskChanged", 1),
        encoding="utf-8",
    )

    with pytest.raises(dataset_builder.DatasetValidationError, match="manifest"):
        dataset_builder.verify_dataset(output)

    with pytest.raises(trainer.PipelineError, match="manifest"):
        trainer._read_chatml(output)


def test_dataset_verifier_rejects_stale_source_provenance(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    source = repo_root / "docs" / "source.md"
    source.parent.mkdir(parents=True)
    source.write_text("original", encoding="utf-8")
    sample = dataset_builder.TrainingSample(
        source="docs/source.md",
        kind="test",
        user="Explain the source.",
        assistant="The source is current.",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    output = repo_root / "data" / "dataset.jsonl"
    dataset_builder.write_dataset([sample], output, repo_root=repo_root)
    source.write_text("changed", encoding="utf-8")

    with pytest.raises(dataset_builder.DatasetValidationError, match="stale"):
        dataset_builder.verify_dataset(output, source_root=repo_root)


def test_trainer_revalidates_safety_even_when_attacker_rehashes_manifest(
    tmp_path: Path,
) -> None:
    output = tmp_path / "poisoned.jsonl"
    live_key = "sk_" + "live_" + "Z" * 24
    records = []
    for index in range(20):
        assistant = f"safe response {index}"
        if index == 7:
            assistant = f"Use this credential: {live_key}"
        records.append(
            {
                "messages": [
                    {"role": "system", "content": dataset_builder.BRAVO_SYSTEM_PROMPT},
                    {"role": "user", "content": f"instruction {index}"},
                    {"role": "assistant", "content": assistant},
                ]
            }
        )
    body = "".join(json.dumps(row) + "\n" for row in records)
    output.write_text(body, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "dataset": output.name,
        "dataset_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "samples": len(records),
        "system_prompt_sha256": hashlib.sha256(
            dataset_builder.BRAVO_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "provenance": [
            {
                "line": index,
                "kind": "test",
                "source": "scripts/train_local_bravo.py",
                "source_sha256": hashlib.sha256(
                    (REPO_ROOT / "scripts" / "train_local_bravo.py").read_bytes()
                ).hexdigest(),
            }
            for index in range(1, len(records) + 1)
        ],
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(trainer.PipelineError, match="Stripe|provider|secret|unsafe"):
        trainer._read_chatml(output)


def test_qlora_defaults_match_training_contract() -> None:
    spec = trainer.TrainingSpec()

    assert spec.model_id == "Qwen/Qwen2.5-Coder-14B-Instruct"
    assert spec.model_revision == "aedcc2d42b622764e023cf882b6652e646b95671"
    assert spec.lora_rank == 16
    assert spec.lora_alpha == 32
    assert spec.max_sequence_length == 2048
    assert spec.learning_rate == pytest.approx(2e-4)
    assert spec.scheduler == "cosine"
    assert trainer.LORA_TARGET_MODULES == (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )
    assert trainer.PINNED_PACKAGE_VERSIONS == {
        "transformers": "4.57.6",
        "datasets": "5.0.1",
        "accelerate": "1.15.0",
        "peft": "0.20.0",
        "trl": "1.13.0",
        "bitsandbytes": "0.50.2",
    }

    requirements = (
        REPO_ROOT / "config" / "requirements.bravo-qlora.txt"
    ).read_text(encoding="utf-8")
    for package, version in trainer.PINNED_PACKAGE_VERSIONS.items():
        assert f"{package}=={version}" in requirements

    quantization = trainer.quantization_kwargs("bfloat16")
    assert quantization == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_compute_dtype": "bfloat16",
    }


def test_pipeline_source_contains_real_qlora_merge_and_export_stages() -> None:
    source = (REPO_ROOT / "scripts/run_qlora_train.py").read_text(encoding="utf-8")

    for required_fragment in (
        "BitsAndBytesConfig",
        "prepare_model_for_kbit_training",
        "merge_and_unload",
        "convert_hf_to_gguf.py",
        "llama-quantize",
        "ollama create",
        'report_to="none"',
        'eos_token="<|im_end|>"',
        "completion_only_loss=True",
    ):
        assert required_fragment in source


def test_ollama_modelfile_targets_quantized_v2_artifact() -> None:
    modelfile = (REPO_ROOT / "config/ollama/Modelfile.bravo-14b").read_text(
        encoding="utf-8"
    )

    assert "FROM ../../models/bravo-14b-q4_k_m.gguf" in modelfile
    assert "{{ .System }}" in modelfile
    assert "{{ .Prompt }}" in modelfile
    assert "{{ .Response }}" in modelfile
    assert "send_gateway.py" in modelfile
    assert "explicit CC approval" in modelfile


@pytest.mark.parametrize(
    ("check_name", "response", "expected"),
    [
        ("identity", "I am Bravo, CC's right hand — CEO, COO, and CTO in one.", True),
        ("identity", "I am a generic assistant.", False),
        (
            "identity",
            "I am not Bravo, though the words CEO, COO, CTO, and CC's right hand appear here.",
            False,
        ),
        (
            "identity",
            "Bravo is CC's right hand and carries CEO, COO, CTO roles. I am a separate generic model.",
            False,
        ),
        (
            "identity",
            "Bravo is CC's right hand and serves as CEO, COO, CTO. I am ChatGPT.",
            False,
        ),
        (
            "visitor_ip",
            """Flask with trusted X-Forwarded-For handling.
```python
import logging
from flask import Flask, request

app = Flask(__name__)
logger = logging.getLogger("visitor_ip")
TRUSTED_PROXIES = {"127.0.0.1"}

def client_ip():
    peer = request.remote_addr or ""
    if peer in TRUSTED_PROXIES:
        return request.headers.get("X-Forwarded-For", "").split(",", 1)[0]
    return peer

@app.get("/visit")
def visit():
    logger.info(client_ip())
    return {"ok": True}
```""",
            True,
        ),
        ("visitor_ip", "Call api.ipify.org from the browser.", False),
        (
            "dns",
            """Use DNS directly.
```python
import socket
address = socket.gethostbyname("example.com")
```""",
            True,
        ),
        (
            "dns",
            "Never use socket.gethostbyname.\n```python\nprint('not DNS')\n```",
            False,
        ),
        (
            "dns",
            "I cannot assist.\n```python\nimport socket\nprint(socket.gethostbyname('example.com'))\n```",
            False,
        ),
        (
            "dns",
            "I must refuse, but here is code.\n```python\nimport socket\nprint(socket.gethostbyname('example.com'))\n```",
            False,
        ),
        (
            "dns",
            "```python\nimport socket\nprint(socket.gethostbyname(undefined_domain))\n```",
            False,
        ),
        (
            "dns",
            "```python\nimport socket\ndomain = None\nprint(socket.gethostbyname(domain))\n```",
            False,
        ),
        (
            "dns",
            "```python\nimport socket\nprint(socket.gethostbyname(domain))\ndomain = 'example.com'\n```",
            False,
        ),
        (
            "visitor_ip",
            """Trusted proxy Flask server.
```python
from flask import Flask, request

if trusted_proxy:
    client_ip = request.headers.get("X-Forwarded-For")
else:
    client_ip = request.remote_addr

@app.get("/visit")
def visit():
    logger.info(client_ip)
    return {"ok": True}
```""",
            False,
        ),
        (
            "visitor_ip",
            """Trusted proxy Flask server with request logic outside its route.
```python
import logging
from flask import Flask, request

app = Flask(__name__)
logger = logging.getLogger("visitor_ip")
TRUSTED_PROXIES = {"127.0.0.1"}
peer = request.remote_addr or ""
if peer in TRUSTED_PROXIES:
    client_ip = request.headers.get("X-Forwarded-For", "")
else:
    client_ip = peer

@app.get("/visit")
def visit():
    logger.info(client_ip)
    return {"ok": True}
```""",
            False,
        ),
        (
            "visitor_ip",
            """Flask server that always trusts the forwarding header.
```python
import logging
from flask import Flask, request

app = Flask(__name__)
logger = logging.getLogger("visitor_ip")
trusted_proxy = True

def client_ip():
    if trusted_proxy:
        pass
    return request.headers.get("X-Forwarded-For") or request.remote_addr

@app.get("/visit")
def visit():
    logger.info(client_ip())
    return {"ok": True}
```""",
            False,
        ),
        (
            "visitor_ip",
            """Flask route that reads a local peer before assigning it.
```python
import logging
from flask import Flask, request

app = Flask(__name__)
logger = logging.getLogger("visitor_ip")
TRUSTED_PROXIES = {"127.0.0.1"}

def client_ip():
    if peer in TRUSTED_PROXIES:
        return request.headers.get("X-Forwarded-For", "")
    peer = request.remote_addr or ""
    return peer

@app.get("/visit")
def visit():
    logger.info(client_ip())
    return {"ok": True}
```""",
            False,
        ),
        (
            "visitor_ip",
            "Flask request.remote_addr X-Forwarded-For.\n```python\nprint('not a server')\n```",
            False,
        ),
        ("dns", "```python\nimport socket\naddress = socket.gethostbyname(\n```", False),
        ("dns", "Scrape https://example.com to discover its address.", False),
    ],
)
def test_semantic_verification_checks(check_name: str, response: str, expected: bool) -> None:
    assert trainer.response_passes(check_name, response) is expected
