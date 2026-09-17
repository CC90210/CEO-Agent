#!/usr/bin/env python3
"""Train, merge, convert, quantize, import, and verify ``bravo-14b-v2``.

The default command is ``train`` so the handover command remains valid::

    python scripts/run_qlora_train.py

The full staged workflow is intentionally explicit::

    python scripts/run_qlora_train.py preflight --stage train
    python scripts/run_qlora_train.py train
    python scripts/run_qlora_train.py merge
    python scripts/run_qlora_train.py convert
    python scripts/run_qlora_train.py quantize
    python scripts/run_qlora_train.py import-ollama
    python scripts/run_qlora_train.py verify

Training is true NF4 QLoRA and fails before any model download when a CUDA GPU
or required package is absent.  A 14B merge needs substantially more than
16 GiB system RAM; export is therefore expected to run on the GPU host and the
Q4_K_M GGUF can then be copied to this Windows Ollama machine.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "Qwen/Qwen2.5-Coder-14B-Instruct"
MODEL_REVISION = "aedcc2d42b622764e023cf882b6652e646b95671"
BRAVO_SYSTEM_PROMPT = (
    "You are Bravo — CC's right hand: CEO, COO, and CTO of OASIS AI Solutions in one."
)
DEFAULT_DATASET = REPO_ROOT / "data" / "bravo_dataset.jsonl"
DEFAULT_ADAPTER_DIR = REPO_ROOT / "models" / "bravo-14b-lora"
DEFAULT_MERGED_DIR = REPO_ROOT / "models" / "bravo-14b-merged"
DEFAULT_F16_GGUF = REPO_ROOT / "models" / "bravo-14b-f16.gguf"
DEFAULT_Q4_GGUF = REPO_ROOT / "models" / "bravo-14b-q4_k_m.gguf"
DEFAULT_MODELFILE = REPO_ROOT / "config" / "ollama" / "Modelfile.bravo-14b"
DEFAULT_OLLAMA_MODEL = "bravo-14b-v2"
LORA_TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)
TRAIN_PACKAGES = ("torch", "transformers", "datasets", "accelerate", "peft", "trl", "bitsandbytes")
MERGE_PACKAGES = ("torch", "transformers", "accelerate", "peft")
PINNED_PACKAGE_VERSIONS = {
    "transformers": "4.57.6",
    "datasets": "5.0.1",
    "accelerate": "1.15.0",
    "peft": "0.20.0",
    "trl": "1.13.0",
    "bitsandbytes": "0.50.2",
}
WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PipelineError(RuntimeError):
    """A clear, expected pipeline failure that should be shown to the operator."""


@dataclass(frozen=True)
class TrainingSpec:
    model_id: str = MODEL_ID
    model_revision: str = MODEL_REVISION
    dataset_path: Path = DEFAULT_DATASET
    adapter_dir: Path = DEFAULT_ADAPTER_DIR
    merged_dir: Path = DEFAULT_MERGED_DIR
    f16_gguf: Path = DEFAULT_F16_GGUF
    q4_gguf: Path = DEFAULT_Q4_GGUF
    modelfile: Path = DEFAULT_MODELFILE
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    lora_rank: int = 16
    lora_alpha: int = 32
    max_sequence_length: int = 2048
    learning_rate: float = 2e-4
    scheduler: str = "cosine"
    epochs: float = 2.0
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    eval_fraction: float = 0.05
    seed: int = 3407


def quantization_kwargs(compute_dtype: str) -> dict[str, Any]:
    """Return serializable NF4 settings; the caller maps dtype to torch."""

    if compute_dtype not in {"float16", "bfloat16"}:
        raise ValueError("compute_dtype must be float16 or bfloat16")
    return {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_compute_dtype": compute_dtype,
    }


def _sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _available_packages(packages: Iterable[str]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for package in packages:
        try:
            found = importlib.util.find_spec(package) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            found = False
        (present if found else missing).append(package)
    return present, missing


def _package_versions(packages: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def _total_memory_gib() -> float | None:
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass
    if platform.system() == "Windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / (1024**3)
        except (AttributeError, OSError):
            return None
    if hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3)
        except (ValueError, OSError):
            return None
    return None


def _free_disk_gib(path: Path) -> float:
    anchor = path
    while not anchor.exists() and anchor.parent != anchor:
        anchor = anchor.parent
    return shutil.disk_usage(anchor).free / (1024**3)


def find_ollama() -> Path | None:
    found = shutil.which("ollama")
    if found:
        return Path(found)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return candidate
    return None


def find_llama_converter(llama_cpp_dir: Path | None = None) -> Path | None:
    roots = []
    configured = os.environ.get("LLAMA_CPP_DIR")
    if llama_cpp_dir:
        roots.append(llama_cpp_dir)
    if configured:
        roots.append(Path(configured))
    roots.extend((REPO_ROOT / "llama.cpp", REPO_ROOT.parent / "llama.cpp"))
    for root in roots:
        candidate = root / "convert_hf_to_gguf.py"
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_quantizer(explicit: Path | None = None, llama_cpp_dir: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    for name in ("llama-quantize", "llama-quantize.exe", "quantize", "quantize.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    configured = os.environ.get("LLAMA_CPP_DIR")
    roots = [
        root
        for root in (
            llama_cpp_dir,
            Path(configured) if configured else None,
            REPO_ROOT / "llama.cpp",
            REPO_ROOT.parent / "llama.cpp",
        )
        if root
    ]
    for root in roots:
        candidates.extend(
            root / relative
            for relative in (
                "llama-quantize.exe",
                "build/bin/llama-quantize",
                "build/bin/llama-quantize.exe",
                "build/bin/Release/llama-quantize.exe",
                "build/Release/llama-quantize.exe",
            )
        )
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        ollama_root = Path(local_app_data) / "Programs" / "Ollama"
        candidates.extend(
            (
                ollama_root / "llama-quantize.exe",
                ollama_root / "lib" / "ollama" / "llama-quantize.exe",
            )
        )
        if ollama_root.is_dir():
            candidates.extend(ollama_root.glob("lib/ollama/*/llama-quantize.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _cuda_status() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"available": False, "reason": "torch is not installed"}
    try:
        import torch

        available = bool(torch.cuda.is_available())
        return {
            "available": available,
            "device_count": int(torch.cuda.device_count()),
            "devices": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
            "torch_version": torch.__version__,
            "torch_cuda": torch.version.cuda,
        }
    except Exception as exc:
        return {"available": False, "reason": f"torch CUDA probe failed: {exc}"}


def preflight(
    stage: str,
    spec: TrainingSpec,
    *,
    llama_cpp_dir: Path | None = None,
    quantizer: Path | None = None,
) -> dict[str, Any]:
    """Return a side-effect-free readiness report for one pipeline stage."""

    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {
        "stage": stage,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "physical_ram_gib": _total_memory_gib(),
        "free_disk_gib": round(_free_disk_gib(REPO_ROOT), 2),
    }
    if stage == "train":
        present, missing = _available_packages(TRAIN_PACKAGES)
        installed_versions = _package_versions(PINNED_PACKAGE_VERSIONS)
        version_mismatches = {
            package: {"expected": expected, "installed": installed_versions[package]}
            for package, expected in PINNED_PACKAGE_VERSIONS.items()
            if installed_versions[package] not in {"missing", expected}
        }
        cuda = _cuda_status()
        details.update(
            {
                "packages_present": present,
                "packages_missing": missing,
                "package_versions": installed_versions,
                "version_mismatches": version_mismatches,
                "cuda": cuda,
            }
        )
        if missing:
            errors.append("missing training packages: " + ", ".join(missing))
        if version_mismatches:
            errors.append(
                "training package versions differ from config/requirements.bravo-qlora.txt"
            )
        if not cuda.get("available"):
            errors.append("CUDA GPU unavailable; 14B NF4 QLoRA is not run on CPU by this pipeline")
        if not spec.dataset_path.is_file():
            errors.append(f"dataset not found: {spec.dataset_path}")
        if details["free_disk_gib"] < 35:
            errors.append("less than 35 GiB free disk for model cache, checkpoints, and adapters")
    elif stage == "merge":
        present, missing = _available_packages(MERGE_PACKAGES)
        details.update({"packages_present": present, "packages_missing": missing})
        if missing:
            errors.append("missing merge packages: " + ", ".join(missing))
        if not spec.adapter_dir.is_dir():
            errors.append(f"adapter directory not found: {spec.adapter_dir}")
        memory = details["physical_ram_gib"]
        if memory is not None and memory < 32:
            errors.append(f"{memory:.1f} GiB RAM is below the 32 GiB merge floor for a 14B FP16 model")
        if details["free_disk_gib"] < 70:
            errors.append("less than 70 GiB free disk for base weights plus merged shards")
    elif stage == "convert":
        converter_path = find_llama_converter(llama_cpp_dir)
        details["converter"] = str(converter_path) if converter_path else None
        if not spec.merged_dir.is_dir():
            errors.append(f"merged model directory not found: {spec.merged_dir}")
        if not converter_path:
            errors.append("llama.cpp/convert_hf_to_gguf.py was not found")
        if details["free_disk_gib"] < 35:
            errors.append("less than 35 GiB free disk for the F16 GGUF")
    elif stage == "quantize":
        quantizer_path = find_quantizer(quantizer, llama_cpp_dir)
        details["quantizer"] = str(quantizer_path) if quantizer_path else None
        if not spec.f16_gguf.is_file():
            errors.append(f"F16 GGUF not found: {spec.f16_gguf}")
        if not quantizer_path:
            errors.append("llama-quantize executable was not found")
        if details["free_disk_gib"] < 12:
            errors.append("less than 12 GiB free disk for the Q4_K_M GGUF")
    elif stage == "import-ollama":
        ollama = find_ollama()
        details["ollama"] = str(ollama) if ollama else None
        if not ollama:
            errors.append("Ollama executable was not found")
        if not spec.q4_gguf.is_file():
            errors.append(f"Q4_K_M GGUF not found: {spec.q4_gguf}")
        if not spec.modelfile.is_file():
            errors.append(f"Ollama Modelfile not found: {spec.modelfile}")
    elif stage == "verify":
        ollama = find_ollama()
        details["ollama"] = str(ollama) if ollama else None
        if not ollama:
            errors.append("Ollama executable was not found")
        else:
            try:
                shown = subprocess.run(
                    [str(ollama), "show", spec.ollama_model],
                    cwd=REPO_ROOT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=60,
                    check=False,
                    creationflags=WINDOWLESS_FLAGS,
                )
            except subprocess.TimeoutExpired:
                details["model_present"] = False
                errors.append(f"Ollama model lookup timed out: {spec.ollama_model}")
            else:
                details["model_present"] = shown.returncode == 0
                if shown.returncode != 0:
                    errors.append(f"Ollama model not found: {spec.ollama_model}")
    else:
        errors.append(f"unknown preflight stage: {stage}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "details": details}


def _require_preflight(
    stage: str,
    spec: TrainingSpec,
    *,
    llama_cpp_dir: Path | None = None,
    quantizer: Path | None = None,
) -> dict[str, Any]:
    report = preflight(stage, spec, llama_cpp_dir=llama_cpp_dir, quantizer=quantizer)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise PipelineError(f"{stage} preflight failed")
    return report


def _dataset_validator_module() -> Any:
    """Load the sibling builder so training cannot bypass its safety gate."""

    expected = (REPO_ROOT / "scripts" / "train_local_bravo.py").resolve()
    existing = sys.modules.get("train_local_bravo")
    if existing is not None and Path(existing.__file__).resolve() == expected:
        return existing

    module_name = "_bravo_dataset_validator"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    module_spec = importlib.util.spec_from_file_location(module_name, expected)
    if module_spec is None or module_spec.loader is None:
        raise PipelineError(f"could not load dataset validator: {expected}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    return module


def _read_chatml(path: Path) -> list[dict[str, Any]]:
    validator = _dataset_validator_module()
    try:
        validator.verify_dataset(path, source_root=REPO_ROOT)
    except (validator.DatasetValidationError, OSError) as exc:
        raise PipelineError(f"dataset safety validation failed: {exc}") from exc

    manifest_path = path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise PipelineError(f"dataset provenance manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"dataset manifest is invalid JSON: {exc.msg}") from exc
    if manifest.get("dataset_sha256") != _sha256_file(path):
        raise PipelineError("dataset content does not match its provenance manifest")

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PipelineError(f"dataset line {line_number} is invalid JSON: {exc.msg}") from exc
            messages = record.get("messages")
            if not isinstance(messages, list) or [message.get("role") for message in messages] != [
                "system",
                "user",
                "assistant",
            ]:
                raise PipelineError(f"dataset line {line_number} is not system/user/assistant ChatML")
            if messages[0].get("content") != BRAVO_SYSTEM_PROMPT:
                raise PipelineError(f"dataset line {line_number} has a non-canonical system prompt")
            records.append(record)
    if len(records) < 20:
        raise PipelineError(f"dataset has only {len(records)} rows; refusing a 14B fine-tune below 20")
    if manifest.get("samples") != len(records):
        raise PipelineError("dataset row count does not match its provenance manifest")
    return records


def _training_manifest(spec: TrainingSpec, metrics: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    serializable_spec = {
        key: str(value) if isinstance(value, Path) else value for key, value in asdict(spec).items()
    }
    return {
        "schema_version": 1,
        "training_spec": serializable_spec,
        "lora_target_modules": list(LORA_TARGET_MODULES),
        "dataset_sha256": _sha256_file(spec.dataset_path),
        "max_observed_tokens": max_tokens,
        "packages": _package_versions(TRAIN_PACKAGES),
        "metrics": metrics,
    }


def train(spec: TrainingSpec, *, resume_from_checkpoint: str | None = None) -> Path:
    _require_preflight("train", spec)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("WANDB_DISABLED", "true")

    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    records = _read_chatml(spec.dataset_path)
    tokenizer = AutoTokenizer.from_pretrained(
        spec.model_id,
        revision=spec.model_revision,
        trust_remote_code=False,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    prepared: list[dict[str, list[dict[str, str]]]] = []
    token_lengths: list[int] = []
    for line_number, record in enumerate(records, 1):
        text = tokenizer.apply_chat_template(
            record["messages"], tokenize=False, add_generation_prompt=False
        )
        token_count = len(tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"])
        if token_count > spec.max_sequence_length:
            raise PipelineError(
                f"dataset line {line_number} is {token_count} tokens; "
                f"limit is {spec.max_sequence_length}. Regenerate instead of truncating."
            )
        prepared.append(
            {
                "prompt": record["messages"][:2],
                "completion": record["messages"][2:],
            }
        )
        token_lengths.append(token_count)

    dataset = Dataset.from_list(prepared)
    split = dataset.train_test_split(test_size=spec.eval_fraction, seed=spec.seed, shuffle=True)
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    compute_dtype_name = "bfloat16" if compute_dtype == torch.bfloat16 else "float16"
    quant_args = quantization_kwargs(compute_dtype_name)
    quant_args["bnb_4bit_compute_dtype"] = compute_dtype
    quantization_config = BitsAndBytesConfig(**quant_args)

    model = AutoModelForCausalLM.from_pretrained(
        spec.model_id,
        revision=spec.model_revision,
        quantization_config=quantization_config,
        device_map={"": torch.cuda.current_device()},
        torch_dtype=compute_dtype,
        trust_remote_code=False,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    lora_config = LoraConfig(
        r=spec.lora_rank,
        lora_alpha=spec.lora_alpha,
        target_modules=list(LORA_TARGET_MODULES),
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    training_args = SFTConfig(
        output_dir=str(spec.adapter_dir),
        max_length=spec.max_sequence_length,
        eos_token="<|im_end|>",
        completion_only_loss=True,
        packing=True,
        num_train_epochs=spec.epochs,
        per_device_train_batch_size=spec.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=spec.gradient_accumulation_steps,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        learning_rate=spec.learning_rate,
        lr_scheduler_type=spec.scheduler,
        warmup_ratio=0.03,
        optim="paged_adamw_8bit",
        weight_decay=0.01,
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        seed=spec.seed,
        report_to="none",
        push_to_hub=False,
    )
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        processing_class=tokenizer,
        peft_config=lora_config,
    )
    result = trainer.train(resume_from_checkpoint=resume_from_checkpoint)
    spec.adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(spec.adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(spec.adapter_dir)
    manifest = _training_manifest(spec, dict(result.metrics), max(token_lengths))
    (spec.adapter_dir / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Training complete; adapter saved to {spec.adapter_dir}")
    return spec.adapter_dir


def merge(spec: TrainingSpec) -> Path:
    _require_preflight("merge", spec)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter_config_path = spec.adapter_dir / "adapter_config.json"
    if not adapter_config_path.is_file():
        raise PipelineError(f"adapter config not found: {adapter_config_path}")
    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    adapter_base = adapter_config.get("base_model_name_or_path")
    if adapter_base and adapter_base != spec.model_id:
        raise PipelineError(
            f"adapter was trained from {adapter_base!r}, not requested base {spec.model_id!r}"
        )

    training_manifest_path = spec.adapter_dir / "training_manifest.json"
    if not training_manifest_path.is_file():
        raise PipelineError(f"training manifest not found: {training_manifest_path}")
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    trained_spec = training_manifest.get("training_spec", {})
    if trained_spec.get("model_revision") != spec.model_revision:
        raise PipelineError(
            "adapter model revision does not match the pinned merge revision"
        )

    base = AutoModelForCausalLM.from_pretrained(
        spec.model_id,
        revision=spec.model_revision,
        torch_dtype=torch.float16,
        device_map={"": "cpu"},
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    peft_model = PeftModel.from_pretrained(base, spec.adapter_dir, device_map={"": "cpu"})
    merged = peft_model.merge_and_unload(progressbar=True, safe_merge=True)
    spec.merged_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(
        spec.merged_dir,
        safe_serialization=True,
        max_shard_size="4GB",
    )
    tokenizer = AutoTokenizer.from_pretrained(spec.adapter_dir, trust_remote_code=False)
    tokenizer.save_pretrained(spec.merged_dir)
    print(f"Merged FP16 Hugging Face model saved to {spec.merged_dir}")
    return spec.merged_dir


def _display_command(command: Sequence[str | os.PathLike[str]]) -> str:
    return subprocess.list2cmdline([os.fspath(part) for part in command])


def _run_checked(
    command: Sequence[str | os.PathLike[str]],
    *,
    timeout_seconds: int | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    printable = _display_command(command)
    print(f"Running: {printable}", flush=True)
    try:
        result = subprocess.run(
            [os.fspath(part) for part in command],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=capture_output,
            timeout=timeout_seconds,
            check=False,
            creationflags=WINDOWLESS_FLAGS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"command timed out after {timeout_seconds}s: {printable}") from exc
    if result.returncode != 0:
        if capture_output:
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        raise PipelineError(f"command exited {result.returncode}: {printable}")
    return result


def convert(spec: TrainingSpec, *, llama_cpp_dir: Path | None = None) -> Path:
    report = _require_preflight("convert", spec, llama_cpp_dir=llama_cpp_dir)
    converter = Path(report["details"]["converter"])
    spec.f16_gguf.parent.mkdir(parents=True, exist_ok=True)
    _run_checked(
        (
            sys.executable,
            converter,
            spec.merged_dir,
            "--outfile",
            spec.f16_gguf,
            "--outtype",
            "f16",
        )
    )
    if not spec.f16_gguf.is_file() or spec.f16_gguf.stat().st_size < 1_000_000_000:
        raise PipelineError("converter returned success but no plausible F16 GGUF was created")
    print(f"F16 GGUF saved to {spec.f16_gguf}")
    return spec.f16_gguf


def quantize(
    spec: TrainingSpec,
    *,
    llama_cpp_dir: Path | None = None,
    quantizer_path: Path | None = None,
    hash_output: bool = True,
) -> Path:
    report = _require_preflight(
        "quantize", spec, llama_cpp_dir=llama_cpp_dir, quantizer=quantizer_path
    )
    quantizer = Path(report["details"]["quantizer"])
    spec.q4_gguf.parent.mkdir(parents=True, exist_ok=True)
    _run_checked((quantizer, spec.f16_gguf, spec.q4_gguf, "Q4_K_M"))
    if not spec.q4_gguf.is_file() or spec.q4_gguf.stat().st_size < 1_000_000_000:
        raise PipelineError("quantizer returned success but no plausible Q4_K_M GGUF was created")
    artifact = {
        "schema_version": 1,
        "path": spec.q4_gguf.name,
        "size_bytes": spec.q4_gguf.stat().st_size,
        "quantization": "Q4_K_M",
        "sha256": _sha256_file(spec.q4_gguf) if hash_output else None,
    }
    spec.q4_gguf.with_suffix(".manifest.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Q4_K_M GGUF saved to {spec.q4_gguf}")
    return spec.q4_gguf


def _modelfile_source(modelfile: Path) -> Path:
    for raw_line in modelfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        keyword, separator, raw_source = line.partition(" ")
        if keyword.upper() != "FROM" or not separator:
            continue
        source_text = raw_source.strip().strip('"').strip("'")
        if not source_text.lower().endswith(".gguf"):
            raise PipelineError("Ollama Modelfile FROM must reference the exported GGUF")
        source = Path(source_text)
        return (source if source.is_absolute() else modelfile.parent / source).resolve()
    raise PipelineError("Ollama Modelfile has no FROM directive")


def import_ollama(spec: TrainingSpec) -> None:
    report = _require_preflight("import-ollama", spec)
    ollama = Path(report["details"]["ollama"])
    expected = _modelfile_source(spec.modelfile)
    if expected != spec.q4_gguf.resolve():
        raise PipelineError(
            f"Modelfile artifact contract resolves to {expected}, but pipeline output is {spec.q4_gguf.resolve()}"
        )
    # Equivalent shell form: ollama create bravo-14b-v2 -f config/ollama/Modelfile.bravo-14b
    _run_checked((ollama, "create", spec.ollama_model, "-f", spec.modelfile))
    _run_checked((ollama, "show", spec.ollama_model), timeout_seconds=60)
    print(f"Ollama model imported as {spec.ollama_model}")


_REFUSAL = re.compile(
    r"(?i)\b(?:as an ai|i (?:cannot|can't|won't)|i am unable to|"
    r"unable to (?:help|provide|write)|cannot assist|"
    r"(?:i\s+)?(?:must|have to|need to)\s+(?:decline|refuse)|"
    r"(?:i\s+)?(?:decline|refuse)\s+(?:to|this|that)|"
    r"not (?:able|allowed) to)\b"
)


def _parsed_python_blocks(response: str) -> list[tuple[str, ast.Module]]:
    blocks = re.findall(r"```python\s*\n(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    parsed: list[tuple[str, ast.Module]] = []
    try:
        for block in blocks:
            tree = ast.parse(block)
            compile(tree, "<ollama-verification>", "exec")
            parsed.append((block, tree))
    except SyntaxError:
        return []
    return parsed


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    cursor: ast.AST | None = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return ".".join(reversed(parts))


def _imports_framework(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] in {"flask", "fastapi"} for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".", 1)[0] in {"flask", "fastapi"}:
                return True
    return False


def _unresolved_names(tree: ast.Module) -> set[str]:
    defined = set(dir(builtins)) | {"__name__", "__file__", "__package__", "__spec__"}
    loaded: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            defined.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            defined.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                defined.update(argument.arg for argument in arguments)
                if node.args.vararg:
                    defined.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined.add(node.args.kwarg.arg)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                loaded.add(node.id)
            else:
                defined.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    return loaded - defined


def _has_obvious_local_use_before_assignment(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    parameters = {
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
    }
    if function.args.vararg:
        parameters.add(function.args.vararg.arg)
    if function.args.kwarg:
        parameters.add(function.args.kwarg.arg)

    stores: dict[str, list[int]] = {}
    loads: dict[str, list[int]] = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Name) or not hasattr(node, "lineno"):
            continue
        target = loads if isinstance(node.ctx, ast.Load) else stores
        target.setdefault(node.id, []).append(node.lineno)
    for name, store_lines in stores.items():
        if name in parameters:
            continue
        if any(line < min(store_lines) for line in loads.get(name, [])):
            return True
    return False


def _is_visitor_ip_server(source: str, tree: ast.Module) -> bool:
    app_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            constructor = _dotted_name(node.value.func).rsplit(".", 1)[-1]
            if constructor in {"Flask", "FastAPI"}:
                app_names.update(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            constructor = _dotted_name(node.value.func).rsplit(".", 1)[-1]
            if constructor in {"Flask", "FastAPI"} and isinstance(node.target, ast.Name):
                app_names.add(node.target.id)

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    route_names: set[str] = set()
    for name, function in functions.items():
        for decorator in function.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner = _dotted_name(decorator.func.value)
            if owner in app_names and decorator.func.attr in {"get", "post", "route"}:
                route_names.add(name)

    relevant_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    pending = list(route_names)
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited or name not in functions:
            continue
        visited.add(name)
        function = functions[name]
        relevant_functions.append(function)
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in functions:
                    pending.append(node.func.id)

    relevant_nodes = [node for function in relevant_functions for node in ast.walk(function)]
    if any(_has_obvious_local_use_before_assignment(function) for function in relevant_functions):
        return False
    attributes = {
        _dotted_name(node).casefold()
        for node in relevant_nodes
        if isinstance(node, ast.Attribute)
    }
    calls = [node for node in relevant_nodes if isinstance(node, ast.Call)]
    constants = {
        node.value.casefold()
        for node in relevant_nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    has_socket_ip = "request.remote_addr" in attributes or "request.client.host" in attributes
    has_forwarded = "x-forwarded-for" in constants
    has_route = bool(route_names)
    has_log = any(
        isinstance(call.func, ast.Attribute) and call.func.attr in {"info", "warning", "write"}
        for call in calls
    )
    peer_names: set[str] = set()
    assignments = [node for node in relevant_nodes if isinstance(node, (ast.Assign, ast.AnnAssign))]
    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            value = assignment.value
            value_attributes = {
                _dotted_name(node).casefold()
                for node in ast.walk(value)
                if isinstance(node, ast.Attribute)
            }
            value_names = {
                node.id for node in ast.walk(value) if isinstance(node, ast.Name)
            }
            is_peer_value = bool(
                {"request.remote_addr", "request.client.host"} & value_attributes
            ) or bool(value_names & peer_names)
            if not is_peer_value:
                continue
            targets: list[ast.AST]
            if isinstance(assignment, ast.Assign):
                targets = assignment.targets
            else:
                targets = [assignment.target]
            before = len(peer_names)
            peer_names.update(
                node.id
                for target in targets
                for node in ast.walk(target)
                if isinstance(node, ast.Name)
            )
            changed = changed or len(peer_names) != before

    def is_trusted_condition(test: ast.AST) -> bool:
        names = {node.id for node in ast.walk(test) if isinstance(node, ast.Name)}
        attributes_in_test = {
            _dotted_name(node).casefold()
            for node in ast.walk(test)
            if isinstance(node, ast.Attribute)
        }
        names_trust_source = any(
            "trusted" in name.casefold() or "proxy" in name.casefold() for name in names
        )
        checks_membership = any(
            isinstance(node, ast.Compare)
            and any(isinstance(operator, (ast.In, ast.NotIn)) for operator in node.ops)
            for node in ast.walk(test)
        ) or any(
            isinstance(node, ast.Call) and _dotted_name(node.func) == "any"
            for node in ast.walk(test)
        )
        checks_peer = bool(names & peer_names) or bool(
            {"request.remote_addr", "request.client.host"} & attributes_in_test
        )
        return names_trust_source and checks_membership and checks_peer

    def is_forwarded_access(node: ast.AST) -> bool:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return (
                node.func.attr == "get"
                and bool(node.args)
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.casefold() == "x-forwarded-for"
            )
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            return (
                isinstance(node.slice.value, str)
                and node.slice.value.casefold() == "x-forwarded-for"
            )
        return False

    forwarded_accesses = [node for node in relevant_nodes if is_forwarded_access(node)]
    has_trust_gate = False
    for condition in (node for node in relevant_nodes if isinstance(node, ast.If)):
        if not is_trusted_condition(condition.test):
            continue
        guarded_nodes = [
            descendant
            for statement in condition.body
            for descendant in ast.walk(statement)
        ]
        if any(access is descendant for access in forwarded_accesses for descendant in guarded_nodes):
            has_trust_gate = True
            break
    return (
        _imports_framework(tree)
        and has_socket_ip
        and has_forwarded
        and has_route
        and has_log
        and has_trust_gate
        and "x-forwarded-for" in source.casefold()
        and not _unresolved_names(tree)
    )


def _calls_socket_gethostbyname(tree: ast.Module) -> bool:
    imports_socket = any(
        isinstance(node, ast.Import)
        and any(alias.name == "socket" and alias.asname in {None, "socket"} for alias in node.names)
        for node in ast.walk(tree)
    )
    if not imports_socket or _unresolved_names(tree):
        return False

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def enclosing_function(node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        cursor = parents.get(node)
        while cursor is not None:
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cursor
            cursor = parents.get(cursor)
        return None

    function_parameters: dict[ast.AST, set[str]] = {}
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        arguments = (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        parameters = {argument.arg for argument in arguments}
        if function.args.vararg:
            parameters.add(function.args.vararg.arg)
        if function.args.kwarg:
            parameters.add(function.args.kwarg.arg)
        function_parameters[function] = parameters

    assignments: dict[tuple[ast.AST | None, str], list[tuple[int, ast.expr]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    key = (enclosing_function(node), target.id)
                    assignments.setdefault(key, []).append((node.lineno, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            key = (enclosing_function(node), node.target.id)
            assignments.setdefault(key, []).append((node.lineno, node.value))

    def viable_hostname(
        expression: ast.expr,
        *,
        scope: ast.FunctionDef | ast.AsyncFunctionDef | None,
        before_line: int,
        seen: set[tuple[ast.AST | None, str]],
    ) -> bool:
        if isinstance(expression, ast.Constant):
            return isinstance(expression.value, str) and bool(expression.value.strip())
        if isinstance(expression, ast.Name):
            if scope is not None and expression.id in function_parameters.get(scope, set()):
                return True
            keys = [(scope, expression.id)]
            if scope is not None:
                keys.append((None, expression.id))
            for key in keys:
                if key in seen:
                    continue
                next_seen = {*seen, key}
                for line, value in assignments.get(key, []):
                    if line < before_line and viable_hostname(
                        value,
                        scope=key[0],
                        before_line=line,
                        seen=next_seen,
                    ):
                        return True
            return False
        return isinstance(
            expression,
            (ast.Call, ast.Subscript, ast.Attribute, ast.BinOp, ast.JoinedStr),
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _dotted_name(node.func).casefold() != "socket.gethostbyname" or not node.args:
            continue
        if viable_hostname(
            node.args[0],
            scope=enclosing_function(node),
            before_line=node.lineno,
            seen=set(),
        ):
            return True
    return False


def response_passes(check_name: str, response: str) -> bool:
    lowered = response.casefold()
    if not response.strip() or _REFUSAL.search(response):
        return False
    if check_name == "identity":
        if re.search(r"\b(?:am|is)\s+not\s+(?:actually\s+)?bravo\b", lowered) or re.search(
            r"\bi(?: am|'m)\s+(?:a\s+)?(?:separate|generic|different|chatgpt|"
            r"codex|claude|gemini|ai|language model)\b",
            lowered,
        ):
            return False
        starts_as_bravo = re.match(
            r"^\s*(?:[*_#>-]+\s*)?(?:i(?: am|'m)\s+bravo|bravo\b)",
            lowered,
        )
        return bool(starts_as_bravo) and all(
            term in lowered for term in ("ceo", "coo", "cto")
        ) and ("cc's right hand" in lowered or "cc’s right hand" in lowered)

    parsed = _parsed_python_blocks(response)
    if not parsed:
        return False
    if check_name == "visitor_ip":
        return any(_is_visitor_ip_server(source, tree) for source, tree in parsed)
    if check_name == "dns":
        return any(_calls_socket_gethostbyname(tree) for _, tree in parsed)
    raise ValueError(f"unknown verification check: {check_name}")


def verify(spec: TrainingSpec) -> dict[str, Any]:
    report = _require_preflight("verify", spec)
    ollama = Path(report["details"]["ollama"])
    _run_checked((ollama, "show", spec.ollama_model), timeout_seconds=60, capture_output=True)
    checks = (
        ("identity", "Who are you?"),
        ("visitor_ip", "Write a python script that logs incoming visitor IP addresses"),
        ("dns", "Write a python script to resolve a domain to an IP"),
    )
    results: list[dict[str, Any]] = []
    for name, prompt in checks:
        completed = _run_checked(
            (ollama, "run", spec.ollama_model, prompt),
            timeout_seconds=900,
            capture_output=True,
        )
        response = completed.stdout.strip()
        passed = response_passes(name, response)
        print(f"\n--- {name} ---\n{response}\n--- pass={passed} ---", flush=True)
        results.append({"check": name, "prompt": prompt, "passed": passed, "response": response})
    output = {"model": spec.ollama_model, "passed": all(item["passed"] for item in results), "results": results}
    results_path = spec.q4_gguf.parent / f"{spec.ollama_model}-verification.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not output["passed"]:
        raise PipelineError(f"one or more Ollama verification gates failed; see {results_path}")
    return output


def _spec_from_args(args: argparse.Namespace) -> TrainingSpec:
    return TrainingSpec(
        model_id=args.model_id,
        model_revision=args.model_revision,
        dataset_path=args.dataset.resolve(),
        adapter_dir=args.adapter_dir.resolve(),
        merged_dir=args.merged_dir.resolve(),
        f16_gguf=args.f16_gguf.resolve(),
        q4_gguf=args.q4_gguf.resolve(),
        modelfile=args.modelfile.resolve(),
        ollama_model=args.ollama_model,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        max_sequence_length=args.max_sequence_length,
        learning_rate=args.learning_rate,
        scheduler=args.scheduler,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        eval_fraction=args.eval_fraction,
        seed=args.seed,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="train",
        choices=("preflight", "train", "merge", "convert", "quantize", "import-ollama", "verify", "all"),
    )
    parser.add_argument("--stage", choices=("train", "merge", "convert", "quantize", "import-ollama", "verify"), default="train")
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--adapter-dir", type=Path, default=DEFAULT_ADAPTER_DIR)
    parser.add_argument("--merged-dir", type=Path, default=DEFAULT_MERGED_DIR)
    parser.add_argument("--f16-gguf", type=Path, default=DEFAULT_F16_GGUF)
    parser.add_argument("--q4-gguf", type=Path, default=DEFAULT_Q4_GGUF)
    parser.add_argument("--modelfile", type=Path, default=DEFAULT_MODELFILE)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--llama-cpp-dir", type=Path)
    parser.add_argument("--quantizer", type=Path)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--max-sequence-length", type=int, default=2048)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--scheduler", default="cosine")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--eval-fraction", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--resume-from-checkpoint")
    parser.add_argument("--skip-artifact-hash", action="store_true")
    return parser


def _validate_args(spec: TrainingSpec) -> None:
    if spec.lora_rank <= 0 or spec.lora_alpha <= 0:
        raise PipelineError("LoRA rank and alpha must be positive")
    if spec.max_sequence_length <= 0:
        raise PipelineError("max sequence length must be positive")
    if spec.learning_rate <= 0 or spec.epochs <= 0:
        raise PipelineError("learning rate and epochs must be positive")
    if spec.batch_size <= 0 or spec.gradient_accumulation_steps <= 0:
        raise PipelineError("batch size and gradient accumulation must be positive")
    if not 0 < spec.eval_fraction < 0.5:
        raise PipelineError("eval fraction must be greater than 0 and less than 0.5")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    spec = _spec_from_args(args)
    try:
        _validate_args(spec)
        if args.command == "preflight":
            report = preflight(
                args.stage,
                spec,
                llama_cpp_dir=args.llama_cpp_dir,
                quantizer=args.quantizer,
            )
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 2
        if args.command in {"train", "all"}:
            train(spec, resume_from_checkpoint=args.resume_from_checkpoint)
        if args.command in {"merge", "all"}:
            merge(spec)
        if args.command in {"convert", "all"}:
            convert(spec, llama_cpp_dir=args.llama_cpp_dir)
        if args.command in {"quantize", "all"}:
            quantize(
                spec,
                llama_cpp_dir=args.llama_cpp_dir,
                quantizer_path=args.quantizer,
                hash_output=not args.skip_artifact_hash,
            )
        if args.command in {"import-ollama", "all"}:
            import_ollama(spec)
        if args.command in {"verify", "all"}:
            verify(spec)
        return 0
    except (PipelineError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
