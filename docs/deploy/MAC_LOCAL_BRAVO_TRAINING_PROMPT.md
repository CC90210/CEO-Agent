---
title: "Mac handover: train and serve bravo-14b-v2"
date: 2026-09-14
author: Bravo
audience: "Codex on CC's Mac"
repo: CEO-Agent
status: ready-for-hardware-gate
tags: [handover, codex, macos, mlx, qlora, ollama, bravo]
---

# HANDOVER TO CODEX: Train `bravo-14b-v2` on CC's Mac

> Give this entire file to the Codex session running on the Mac. The receiving
> agent should execute it as an operational runbook, maintain a visible plan,
> and report actual command output at each gate. Do not treat it as background
> reading.

## 0. Receiving-agent contract

You are Codex running locally on CC's Mac. Your mission is to build, test, and
serve a Mac-native fine-tuned Bravo model without degrading CC's Windows PC.
Work in the canonical Mac checkout at `~/CEO-Agent` unless live inspection
shows that the active checkout is elsewhere.

Before changing anything:

1. Read `AGENTS.md`, then follow its operational boot directive.
2. Inspect `git status --short`; preserve all existing user changes.
3. Create a plan with exactly one item in progress.
4. Read every file before editing it and verify every edit.
5. Never read or copy `.env.agents`, tokens, customer exports, or credentials
   into model context.
6. Keep all model weights, datasets, adapters, and evaluation output private.
   Do not upload them to a public Hugging Face or Ollama repository.
7. Do not call a model `bravo-14b-v2` until the real trained GGUF has been
   imported and all final gates pass. A renamed base model is not a trained v2.
8. Do not install or start production schedulers, Telegram bots, PM2 daemons,
   or Windows-owned cron services on the Mac. This task covers local training,
   local Ollama, the standalone terminal client, and the per-machine dashboard
   bridge only.

If this document conflicts with live source code, verify the source and report
the discrepancy before continuing. Evidence beats this handover.

## 1. Mission and definition of the model

Build `bravo-14b-v2` for these measured capabilities:

- Correct backend and network code: DNS resolution, HTTP access, trusted-proxy
  visitor-IP handling, rate limiting, async webhooks, JWT validation, and
  SQLite/Turso patterns.
- Business-Empire-Agent awareness: Bravo identity, script and skill catalog,
  tool-routing rules, outbound gates, and untrusted-content boundaries.
- Direct answers to benign, authorized technical requests without irrelevant
  refusal lectures or corporate disclaimer padding.
- Complete Python 3.12 and TypeScript examples without fake execution results.

Operational safety remains in force. Fine-tuning must not teach the model to
bypass approval for sends, money movement, destructive changes, production
deployments, or secret access.

Target pipeline:

```text
570-row private ChatML corpus
        -> deterministic train/valid/test split
        -> Apple MLX-LM 4-bit QLoRA
        -> tested LoRA adapter
        -> fused/dequantized Qwen2.5 model
        -> llama.cpp F16 GGUF conversion
        -> Q4_K_M quantization
        -> Ollama tag bravo-14b-v2
        -> terminal and dashboard-harness verification
```

## 2. Verified starting state on Windows

This state was measured on 2026-09-14. Re-check anything that matters at
execution time.

### What exists

- Windows runner: Ollama `0.34.0`.
- Preserved Ollama tags:
  - `bravo-14b:latest`
  - `richardyoung/qwen2.5-coder-14b-instruct-abliterated:latest`
- Both tags share the same underlying blob. The full Windows model store is
  `C:\Users\User\.ollama\models`: 8 files and 8,988,113,747 bytes
  (about 8.37 GiB), not 18 GiB.
- The source checkout is on branch `fix/smtp-third-door` at `b63a1934`, with
  remote `https://github.com/CC90210/CEO-Agent.git`.
- `data/bravo_dataset.jsonl` contains 570 valid ChatML rows, maximum sample
  length 2,497 characters, SHA-256
  `a1adf858a8809e51464e908cb7a35c2444ffcf8ae07c145c6f75145fd3fe79ca`.
- Focused verification on Windows passed: `35 passed, 1 warning`.

Corpus composition:

| Kind | Rows |
| --- | ---: |
| Script catalog summaries | 379 |
| Skill catalog summaries | 165 |
| Persona rules | 13 |
| Curated backend code | 10 |
| Direct execution | 1 |
| Identity | 1 |
| Network concepts | 1 |

This gives broad catalog awareness but only ten curated backend-code examples.
Improvement must be benchmarked; it must not be assumed from row count.

### What does not exist

- `bravo-14b-v2` has not been trained or imported anywhere.
- `models/` does not yet exist in the Windows checkout.
- `llama.cpp/` does not exist in the Windows checkout.
- No LoRA adapter, merged model, F16 GGUF, Q4_K_M GGUF, or v2 verification
  report exists.
- `config/ollama/Modelfile.bravo-14b` points to the intentionally absent
  `models/bravo-14b-q4_k_m.gguf`. Never run `ollama create` until that file is
  present and verified.

### Windows retirement state

The Windows source session audited the local runtime before retiring it:

- `ollama ps` was empty; no model was loaded.
- Only the idle Ollama app/server pair was running, using about 30.5 MiB total
  working set and listening only on `127.0.0.1:11434`.
- There was no Ollama service, scheduled task, Registry Run/RunOnce entry,
  StartupApproved entry, or Startup-folder item.
- The unrelated `Bravo Claude Spillover`, `Bravo Console`, and `Bravo Fleet
  Watchdog` startup components belong to the active Bravo harness and must stay
  enabled.
- The source session attempted to stop only those two processes, but both
  PowerShell `Stop-Process` and native `taskkill` were denied by Windows. CC
  must use the official tray action, **Quit Ollama**, once; no elevated or
  destructive workaround is authorized. The source session then verifies the
  process/listener state if it is still active.
- No uninstall, tag deletion, model-file deletion, CPU-mode environment
  change, or Bravo-harness change is part of the retirement.

After that tray exit, Windows is an archive for the old model, not a training
or inference host. Do not remotely restart Ollama there during this Mac task.

## 3. Critical truth-state warnings

### 3.1 The training bundle is local and untracked

At handover time, every new training artifact below is untracked in the Windows
checkout. A fresh clone from `origin` will not contain it:

```text
scripts/train_local_bravo.py
scripts/run_qlora_train.py
scripts/bravo_cli.py
scripts/tests/test_local_bravo_training.py
config/requirements.bravo-qlora.txt
config/ollama/Modelfile.bravo-14b
data/bravo_dataset.jsonl
data/bravo_dataset.manifest.json
```

The handover itself is also local until it is transferred or committed. The
eight files above are only the training-specific bundle. Their hashes prove
transfer integrity; they do **not** make the run reproducible by themselves.

At handover time the source checkout was:

```text
repo:   https://github.com/CC90210/CEO-Agent.git
branch: fix/smtp-third-door
HEAD:   b63a1934
remote branch HEAD: 0949ce5c
local-only commits: 12
```

The corpus also depends on the repository sources it mined. A fresh clone of
the remote branch is missing the 12 local commits, and these manifest-relevant
paths had working-tree content that must be preserved exactly:

```text
scripts/bravo_cli.py
scripts/core/event_retention.py
scripts/harness_eval.py
scripts/integrations/email_engine.py
scripts/lead_generation/enrich_owner_names.py
scripts/run_qlora_train.py
scripts/scheduler.py
scripts/train_local_bravo.py
```

Do not start from a fresh Mac clone plus only the eight files and silently
recreate the rest from memory. Obtain both of these from the Windows source
session through a private transfer:

1. A Git bundle/private branch containing commit `b63a1934` and its 12
   local-only commits.
2. A reviewed, allowlisted overlay containing every uncommitted source named
   by `data/bravo_dataset.manifest.json`, including the paths above and the
   eight-file training bundle.

Do not commit unrelated working-tree changes just to move them. Do not copy
`.env.agents`, `.git/`, credentials, caches, Ollama blobs, or model weights in
the overlay. If the complete sanitized source snapshot is not available,
**stop and request it from CC/source Codex**; do not regenerate the corpus from
a materially different checkout.

Raw Windows bundle checksums at handover time:

```text
d5de8945059a52d86226877e9253e94c504a99551c4e50dfe17356b7d50ae7ab  scripts/train_local_bravo.py
8e7e1074ae8fce863400b498d28c089affa91e9a290f7f5929b074472e32aff0  scripts/run_qlora_train.py
2fa650fb13c1971412c000328b8f19cd6a7862d1d39f3e2774ed0788515f9845  scripts/bravo_cli.py
d4f9d107f6e36fa3b0432d7eaf079386f594bd6d033d480a2927803f7e4c394e  scripts/tests/test_local_bravo_training.py
afbbeb22563f9b31a418c2c82f9d53c5e6f6b598637e686fdc293a51ba4226fe  config/requirements.bravo-qlora.txt
186df52ffbbc3427bd96224b2602cb45444575178a044389dc7ff37b858fbff7  config/ollama/Modelfile.bravo-14b
a1adf858a8809e51464e908cb7a35c2444ffcf8ae07c145c6f75145fd3fe79ca  data/bravo_dataset.jsonl
158ed0c921ead5bf31f00ae9384fe11a423163c58964a1661ed3ddde8261b361  data/bravo_dataset.manifest.json
```

Use `shasum -a 256 <paths...>` on the raw transferred files. Git line-ending
conversion or an intentional provenance fix may change source-file and manifest
hashes later; record every intentional new hash.

### 3.2 The existing CUDA trainer is not the Mac trainer

`scripts/run_qlora_train.py` is a CUDA, PyTorch, bitsandbytes, PEFT, and TRL
pipeline. Its preflight deliberately refuses CPU/MPS training. Keep it as the
NVIDIA/rented-GPU fallback and as the existing Ollama verification harness, but
do not weaken its CUDA check or pretend it is Metal-native.

The Mac implementation must use MLX-LM. MLX-LM officially supports QLoRA,
Qwen2-family models, ChatML JSONL, prompt masking, and gradient checkpointing:

- https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md
- https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/examples/lora_config.yaml
- https://ml-explore.github.io/mlx/build/html/install.html

### 3.3 The current planned base is not the old abliterated tag

The CUDA runner pins the official base
`Qwen/Qwen2.5-Coder-14B-Instruct` at revision
`aedcc2d42b622764e023cf882b6652e646b95671`. The practical Mac starting point
is the 4-bit MLX conversion
`mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`, derived from that official
model family:

- https://huggingface.co/mlx-community/Qwen2.5-Coder-14B-Instruct-4bit

This is not proof of abliterated lineage. Default to the official aligned base
and teach concise behavior for benign technical work through reviewed data and
the system prompt. If CC explicitly requires an abliterated base, stop and
identify a verifiable Hugging Face/MLX source, license, original revision, and
Qwen2 compatibility first. Never label the official-base result abliterated.

### 3.4 The current provenance manifest is line-ending-sensitive

`scripts/train_local_bravo.py::_source_sha256()` hashes raw file bytes. The
Windows checkout has `core.autocrlf=true`, and many Markdown sources are CRLF.
A normal Mac LF checkout can therefore produce `stale source provenance` even
when the text is logically identical.

Fix this before training:

1. Add a failing regression test proving that LF and CRLF versions of the same
   textual source produce the same provenance hash.
2. Normalize `\r\n` and lone `\r` to `\n` inside `_source_sha256()` before
   hashing textual sources.
3. Regenerate `data/bravo_dataset.jsonl` and its manifest on the Mac.
4. Re-run the full focused test file and dataset verifier.
5. Record the regenerated dataset and manifest hashes.

Do not simply disable provenance verification. The manifest is the guard that
ties training rows to reviewed sources.

### 3.5 Do not use the legacy 50-row corpus

Do not train on `data/training/bravo_harness_sft.jsonl`. It contains fabricated
mutation outcomes, including an invented successful email queue result, which
violates the current evidence and outbound rules. The only approved source
corpus for this run is `data/bravo_dataset.jsonl` after successful regeneration
and verification.

### 3.6 The standalone launcher has Mac performance and file-read traps

`scripts/bravo_cli.py` currently forces these values only when it auto-starts
Ollama:

```text
OLLAMA_LLM_LIBRARY=cpu
OLLAMA_NUM_GPU=0
OLLAMA_VULKAN=false
```

That behavior was intentional for the old Windows CPU host but would disable
the Mac's accelerated path. Before declaring the standalone Mac harness ready,
make server-launch environment selection platform-aware and add a test:

- Windows may retain its explicit CPU fallback.
- macOS must not set `OLLAMA_LLM_LIBRARY=cpu` or `OLLAMA_NUM_GPU=0`.
- Prefer connecting to an already running Mac Ollama app/server.
- Keep `BRAVO_MODEL` as the explicit model selector; do not silently change the
  global default for other machines.

The launcher's `/read` command is not approved for use on the Mac in its
current form. It can accept traversal/absolute paths and can inject file
contents into a prompt without an adequate secret boundary. Before using the
standalone client, add failing security tests and then patch it so that it:

- resolves every requested path canonically under `REPO_ROOT`;
- rejects absolute paths outside the repo, `..` traversal, and symlink escapes;
- blocks `.env*`, credentials/key material, `.git`, `.ollama`, model binaries,
  and the repository's existing secret-deny patterns;
- rejects binary/non-text content and enforces a conservative byte limit; and
- reuses existing path/secret guards where available instead of creating a
  second security policy.

The tests must prove rejection of `/read .env.agents`, a `../../` escape, an
absolute outside-repo path, and an in-repo symlink pointing outside, plus
successful reading of one harmless in-repo text file. Do not open
`scripts/bravo_cli.py` interactively until these tests pass. The dashboard
bridge is a separate route and may be verified after its pairing/authentication
gate in section 13.

## 4. Phase A: Mac hardware and space gate

Run these commands yourself on the Mac and save the output in the task log:

```bash
cd ~/CEO-Agent
uname -m
sw_vers
system_profiler SPHardwareDataType | grep -E "Chip|Memory"
sysctl -n hw.memsize
df -h .
xcode-select -p
git status --short
git remote -v
git branch --show-current
git rev-parse --short HEAD
```

Go/no-go rules:

| Mac | Decision |
| --- | --- |
| Intel or under 32 GB unified memory | Stop. Use a rented NVIDIA GPU with `scripts/run_qlora_train.py`. |
| 32/36 GB Apple Silicon | Pilot only. Full fusion/export may swap heavily; recommend rented GPU unless CC accepts the slower, constrained path. |
| 48 GB Apple Silicon | Proceed with batch size 1, gradient accumulation, checkpointing, and monitoring. |
| 64 GB or more Apple Silicon | Preferred local route. |

Require macOS 14 or newer and approximately 100 GiB of free space before the
full path. The 4-bit base is about 8.3 GB, while caches, adapters, a dequantized
model, F16 GGUF, Q4 GGUF, and temporary conversion data can coexist.

If the gate fails, do not install a large model or let the machine swap for
hours. Report the measured chip, memory, free disk, and the rented-GPU fallback.

## 5. Phase B: Transfer and source-integrity gate

After the private Git bundle/branch and allowlisted overlay have reached the
Mac, prove that the source snapshot is present **before editing anything**:

```bash
cd ~/CEO-Agent
git cat-file -e 'b63a1934^{commit}'
git rev-parse --verify 'b63a1934^{commit}'
git branch --show-current
git status --short
```

The resolved commit must be the transferred Windows `b63a1934` commit, and the
initial branch/HEAD plus overlay file list must be recorded. If `git cat-file`
fails, stop: the Mac has only the public/remote snapshot, not the local source
lineage that produced the dataset. After applying the overlay, verify every
non-`curated/` source named in `data/bravo_dataset.manifest.json` exists. The
dataset verifier must then bind those files to the manifest; a successful
eight-file checksum alone is insufficient.

Verify the training-specific bundle:

```bash
cd ~/CEO-Agent
for f in \
  scripts/train_local_bravo.py \
  scripts/run_qlora_train.py \
  scripts/bravo_cli.py \
  scripts/tests/test_local_bravo_training.py \
  config/requirements.bravo-qlora.txt \
  config/ollama/Modelfile.bravo-14b \
  data/bravo_dataset.jsonl \
  data/bravo_dataset.manifest.json; do
  test -s "$f" || { echo "MISSING: $f"; exit 1; }
done

shasum -a 256 \
  scripts/train_local_bravo.py \
  scripts/run_qlora_train.py \
  scripts/bravo_cli.py \
  scripts/tests/test_local_bravo_training.py \
  config/requirements.bravo-qlora.txt \
  config/ollama/Modelfile.bravo-14b \
  data/bravo_dataset.jsonl \
  data/bravo_dataset.manifest.json
```

Before creating a virtual environment, split data, adapter, or model, protect
the repository from large/private build output. Inspect the existing
`.gitignore`, then use `apply_patch` to add only missing entries:

```text
/models/
/.venv-mlx/
/data/bravo_mlx/
```

Do not add a broad `/data/` rule and do not silently ignore the source dataset
or provenance manifest. Prove all three output paths are ignored:

```bash
git check-ignore -v --no-index models/probe.gguf
git check-ignore -v --no-index .venv-mlx/probe
git check-ignore -v --no-index data/bravo_mlx/probe.jsonl
```

Then implement the line-ending-independent provenance test/fix from section
3.4 with `apply_patch`, regenerate, and verify:

```bash
python3 scripts/train_local_bravo.py
python3 scripts/train_local_bravo.py --verify data/bravo_dataset.jsonl
python3 -m pytest -q -p no:cacheprovider scripts/tests/test_local_bravo_training.py
```

Expected logical result: 570 valid ChatML records unless a reviewed source
change legitimately changes the count. Any count/hash change must be explained,
not waved through.

Also run a safe secret-pattern scan on the generated corpus using the existing
tests. Never inspect `.env.agents` to perform this check.

## 6. Phase C: Prepare deterministic MLX data

MLX-LM expects a data directory containing `train.jsonl`, optional
`valid.jsonl`, and `test.jsonl`. Create:

```text
scripts/prepare_bravo_mlx_data.py
scripts/tests/test_prepare_bravo_mlx_data.py
data/bravo_mlx/train.jsonl
data/bravo_mlx/valid.jsonl
data/bravo_mlx/test.jsonl
data/bravo_mlx/split_manifest.json
```

Requirements for the splitter:

1. Read `data/bravo_dataset.jsonl` and its provenance manifest together.
2. Use seed `3407` and a deterministic 90/5/5 split.
3. Stratify by provenance `kind` where group size permits; singleton categories
   remain in training.
4. Keep each record unchanged in OpenAI/Qwen chat format with exactly ordered
   `system`, `user`, and `assistant` messages.
5. Never train on the test set.
6. Write source dataset SHA-256, row assignments, kind counts, seed, and output
   hashes to `split_manifest.json`.
7. Fail closed on duplicates, blank content, invalid roles, missing provenance,
   or sensitive-pattern hits.
8. Add deterministic and schema tests before using the split.

Run and prove:

```bash
python3 scripts/prepare_bravo_mlx_data.py
python3 -m pytest -q -p no:cacheprovider \
  scripts/tests/test_local_bravo_training.py \
  scripts/tests/test_prepare_bravo_mlx_data.py
wc -l data/bravo_mlx/*.jsonl
```

## 7. Phase D: Install an isolated Mac-native toolchain

Do not install CUDA PyTorch or bitsandbytes for the Mac path. Use a dedicated
environment so this work does not alter the Bravo production environment:

```bash
cd ~/CEO-Agent
command -v clang
xcode-select -p
if ! command -v cmake >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 || {
    echo "BLOCKED: CMake is missing and Homebrew is unavailable" >&2
    exit 1
  }
  brew install cmake
fi
cmake --version
python3 -m venv .venv-mlx
source .venv-mlx/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install "mlx-lm[train]" huggingface-hub pyyaml
mlx_lm.lora --help
mlx_lm.fuse --help
python -m pip freeze | sort
```

Install Ollama from its current official macOS instructions, not a random
download mirror:

- https://docs.ollama.com/macos

Ollama's Mac app may register a login item. Keep it on-demand unless CC asks
for an always-on local model: disable its login item after final testing, and
start Ollama manually only when using the model or local dashboard route.

Prepare llama.cpp outside the tracked repo or in a clearly ignored tool cache.
Record its exact commit. Build its Metal-capable tools and verify the current
converter/quantizer CLI before using commands from this handover:

```bash
if [ -e ../llama.cpp ]; then
  test -d ../llama.cpp/.git || {
    echo "BLOCKED: ../llama.cpp exists but is not a Git checkout" >&2
    exit 1
  }
  git -C ../llama.cpp remote -v
  git -C ../llama.cpp status --short
else
  git clone https://github.com/ggml-org/llama.cpp.git ../llama.cpp
fi

cd ../llama.cpp
git remote get-url origin
LLAMA_CPP_COMMIT="$(git rev-parse HEAD)"
printf 'llama.cpp commit: %s\n' "$LLAMA_CPP_COMMIT"
# Record this exact commit in the training manifest. Do not pull/change it
# during conversion; future reruns must check out this recorded commit.
python -m pip install -r requirements.txt
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j
python3 convert_hf_to_gguf.py --help
./build/bin/llama-quantize --help
cd ~/CEO-Agent
```

Primary references:

- https://github.com/ggml-org/llama.cpp/blob/master/convert_hf_to_gguf.py
- https://github.com/ggml-org/llama.cpp/blob/master/conversion/qwen.py
- https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- https://docs.ollama.com/import

Pin the successful MLX-LM, MLX, Python, llama.cpp commit, and Ollama versions in
a training manifest. Do not blindly copy the Windows CUDA dependency file into
the Mac environment.

## 8. Phase E: Baseline benchmark before training

Resolve and record the exact Hugging Face revision for
`mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`. Download/load it only after the
hardware and disk gates pass.

Do not train from a floating Hub ID. Resolve it once, download that immutable
snapshot, record the revision, and use the local snapshot path for baseline,
training, evaluation, and fusion:

```bash
cd ~/CEO-Agent
source .venv-mlx/bin/activate
export MLX_BASE_ID="mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
export MLX_BASE_DIR="models/base/qwen2.5-coder-14b-instruct-4bit"
export MLX_BASE_REV="$(python - <<'PY'
from huggingface_hub import model_info
print(model_info("mlx-community/Qwen2.5-Coder-14B-Instruct-4bit").sha)
PY
)"
test -n "$MLX_BASE_REV"
python - <<'PY'
import os
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=os.environ["MLX_BASE_ID"],
    revision=os.environ["MLX_BASE_REV"],
    local_dir=os.environ["MLX_BASE_DIR"],
)
print(f"downloaded revision {os.environ['MLX_BASE_REV']}")
PY
```

Write the Hub ID, resolved revision, download timestamp, and local snapshot
path to the private training manifest. The upstream Qwen model/revision may be
recorded as declared lineage, but do not claim the MLX conversion is byte-for-
byte identical to upstream without independently proving it.

Create one reusable evaluator rather than ad hoc terminal screenshots. It must
apply the tokenizer's chat template and save raw prompts, raw outputs, timing,
model/revision, and deterministic checks. Benchmark the untouched base on at
least:

1. `Who are you?`
2. `Write a Python script that resolves a domain to an IP address.`
3. `Write a Flask or FastAPI endpoint that logs incoming visitor IP addresses behind an explicitly configured trusted proxy.`
4. `Write a per-client rate limiter that returns HTTP 429 and explain its concurrency boundary.`
5. `How must Bravo send an outbound email in Business-Empire-Agent?`
6. One async webhook, JWT, and SQLite/Turso task from the held-out set.
7. A small generic coding regression set unrelated to Bravo.

Checks must distinguish:

- DNS resolution via `socket.getaddrinfo()`/`socket.gethostbyname()` from HTTP
  scraping or public-IP discovery.
- Direct peer IP from `X-Forwarded-For`, which is trusted only behind an
  explicitly configured reverse proxy.
- Code generation from real execution. The model must not invent successful
  sends, database writes, tests, or deployments.
- Concise authorized technical help from irrelevant disclaimer/refusal text.

Save the base result under `models/evals/bravo-14b-base/`. This is the before
measurement; do not tune the test set after reading failures repeatedly.

## 9. Phase F: Implement and pilot the MLX QLoRA run

Create a Mac-specific runner/config rather than weakening the CUDA runner:

```text
scripts/run_mlx_train.py
scripts/tests/test_run_mlx_train.py
config/mlx/bravo-14b.yaml
models/bravo-14b-mlx-adapters/
```

The runner must preflight Apple Silicon, macOS version, unified memory, free
disk, dataset/manifest integrity, MLX packages, model revision, output paths,
and accidental overwrite of an existing adapter.

Starting MLX configuration, subject to validation against the installed
MLX-LM schema:

```yaml
model: "models/base/qwen2.5-coder-14b-instruct-4bit"
train: true
fine_tune_type: lora
data: "data/bravo_mlx"
seed: 3407
num_layers: 16
batch_size: 1
grad_accumulation_steps: 8
iters: 1032
val_batches: -1
learning_rate: 0.0002
steps_per_report: 5
steps_per_eval: 20
save_every: 20
max_seq_length: 2048
grad_checkpoint: true
mask_prompt: true
adapter_path: "models/bravo-14b-mlx-adapters"
lora_parameters:
  keys:
    - self_attn.q_proj
    - self_attn.k_proj
    - self_attn.v_proj
    - self_attn.o_proj
    - mlp.gate_proj
    - mlp.up_proj
    - mlp.down_proj
  rank: 16
  scale: 2.0
  dropout: 0.0
```

Why `scale: 2.0`: MLX applies LoRA scale directly; it corresponds to the PEFT
target `lora_alpha / rank = 32 / 16`.

MLX-LM advances one microbatch per iteration and applies an optimizer update
after `grad_accumulation_steps`. Therefore `130` would see only about one
quarter of the corpus and is not a two-epoch run. Recompute `iters` from the
actual training split and round it up to a complete accumulation boundary:

```text
iters = ceil((train_rows * epochs) / (batch_size * grad_accumulation_steps))
        * grad_accumulation_steps
```

For 513 training rows, two epochs, batch size 1, and accumulation 8, this is
`ceil(1026 / 8) * 8 = 1032` micro-iterations (129 optimizer updates). If the
deterministic split produces a different row count, change `1032` accordingly;
the final value must be a multiple of 8. Record the installed MLX-LM iteration
semantics and calculation in the training manifest. Configure a cosine
schedule matching the target 2e-4 learning rate only after validating the
installed version's YAML syntax. Do not silently fall back to another schedule.

First run a 16-iteration pilot so it ends on an accumulation boundary. It must
prove:

- the model and tokenizer load;
- all seven intended module families receive adapters;
- prompt masking is active;
- loss is finite and reported;
- a checkpoint can be saved and reloaded;
- memory pressure and swap remain acceptable;
- Ctrl+C/checkpoint recovery does not corrupt the adapter directory.

Monitor with `memory_pressure`, `vm_stat`, `sysctl vm.swapusage`, and process
RSS. Stop the pilot if the Mac becomes unresponsive or sustained swap growth
shows the hardware gate was too optimistic. Do not push through thermal or
memory instability merely to finish locally.

## 10. Phase G: Full training and adapter verification

After the pilot passes, run the full configuration with logging and checkpoint
retention. Keep the Mac awake for the scoped command, not permanently:

```bash
cd ~/CEO-Agent
source .venv-mlx/bin/activate
caffeinate -i python3 scripts/run_mlx_train.py train \
  --config config/mlx/bravo-14b.yaml
```

The exact command may change based on the implemented runner, but the config,
model revision, dataset hashes, and output paths must remain explicit.

Write `models/bravo-14b-mlx-adapters/training_manifest.json` with:

- base model ID and resolved revision;
- original upstream model/revision if known;
- dataset and split hashes/counts;
- Git HEAD and dirty-file list;
- chip, unified memory, macOS, Python, MLX, MLX-LM, Ollama, and llama.cpp
  versions;
- complete hyperparameters and command;
- start/end timestamps, checkpoints, training/validation metrics, and peak
  memory/swap observations.

Evaluate the adapter with the exact same evaluator and prompts used for the
base. Save results under `models/evals/bravo-14b-adapter/`.

Do not proceed to fusion unless:

- Bravo/persona and backend-target checks materially improve or meet their
  explicit threshold;
- generic coding results do not materially regress;
- generated Python examples parse/compile;
- outputs contain no invented execution receipts;
- held-out loss is finite and not clearly diverging.

If the adapter does not improve the benchmark, report that result. Do not hide
it by changing the alias or moving the failed prompts into the training set.

## 11. Phase H: Fuse, convert, and quantize

MLX-LM can fuse/dequantize the adapter, but its built-in GGUF export currently
supports only Llama-, Mistral-, and Mixtral-style models. It explicitly rejects
Qwen model types. Do not use `mlx_lm.fuse --export-gguf` for this Qwen model.

Reference:

- https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/fuse.py

Use this gated path:

1. Fuse and dequantize into `models/bravo-14b-mlx-fused/`.
2. Load that fused model with MLX and re-run a short benchmark. If it differs
   materially from adapter inference, stop.
3. Confirm the output is a complete, HF-compatible Qwen2 safetensors directory
   with tokenizer/config files.
4. Run the pinned llama.cpp `convert_hf_to_gguf.py` after checking its live
   `--help` and Qwen2 converter support.
5. Produce `models/bravo-14b-f16.gguf`.
6. Load/smoke-test the F16 GGUF before quantization where hardware permits.
7. Quantize to `models/bravo-14b-q4_k_m.gguf` with `Q4_K_M`.
8. Compute SHA-256 and write a GGUF manifest with source adapter/fused hashes,
   llama.cpp commit, quantization, size, and smoke results.

Expected command shapes, not substitutes for live `--help`:

```bash
mlx_lm.fuse \
  --model models/base/qwen2.5-coder-14b-instruct-4bit \
  --adapter-path models/bravo-14b-mlx-adapters \
  --save-path models/bravo-14b-mlx-fused \
  --dequantize

python3 ../llama.cpp/convert_hf_to_gguf.py \
  models/bravo-14b-mlx-fused \
  --outfile models/bravo-14b-f16.gguf \
  --outtype f16

../llama.cpp/build/bin/llama-quantize \
  models/bravo-14b-f16.gguf \
  models/bravo-14b-q4_k_m.gguf \
  Q4_K_M

shasum -a 256 models/bravo-14b-f16.gguf models/bravo-14b-q4_k_m.gguf
```

The MLX-fused-to-llama.cpp Qwen bridge is a required pilot gate, not a promised
one-command path. If llama.cpp rejects the MLX-fused layout or the converted
model fails inference, stop. The recommended fallback is to take the verified
adapter/data/config to a rented NVIDIA host and use the existing PEFT merge and
llama.cpp stages there. Do not patch tensor names by guesswork.

## 12. Phase I: Import into Ollama as a new model

Preconditions:

```bash
test -s models/bravo-14b-q4_k_m.gguf
test -s models/bravo-14b-q4_k_m.manifest.json
grep -F "FROM ../../models/bravo-14b-q4_k_m.gguf" \
  config/ollama/Modelfile.bravo-14b
```

The GGUF manifest must contain at least `gguf_sha256` and `gguf_size_bytes`.
Before import, independently recompute both and make the verifier fail on a
missing artifact, missing manifest, size mismatch, or hash mismatch. Record the
values without dumping any unrelated local metadata:

```bash
Q4_SHA="$(shasum -a 256 models/bravo-14b-q4_k_m.gguf | awk '{print $1}')"
Q4_SIZE="$(stat -f '%z' models/bravo-14b-q4_k_m.gguf)"
printf 'Q4 SHA-256: %s\nQ4 bytes: %s\n' "$Q4_SHA" "$Q4_SIZE"
```

Start Ollama on the Mac only now, then import a new tag without replacing any
base tag:

```bash
ollama create bravo-14b-v2 -f config/ollama/Modelfile.bravo-14b
ollama show bravo-14b-v2
ollama list
```

Cryptographically bind the created Ollama tag to this exact GGUF. Ollama's
generated Modelfile should reference a content-addressed blob whose digest is
the GGUF SHA-256:

```bash
Q4_SHA="$(shasum -a 256 models/bravo-14b-q4_k_m.gguf | awk '{print $1}')"
ollama show --modelfile bravo-14b-v2 > models/bravo-14b-v2.resolved.Modelfile
grep -F "sha256-${Q4_SHA}" models/bravo-14b-v2.resolved.Modelfile
```

If that exact digest is absent, stop and inspect the import; do not accept the
tag based on its name or answers alone.

Ollama's official GGUF/Modelfile path is documented here:

- https://docs.ollama.com/import
- https://docs.ollama.com/modelfile

Do not use `ollama cp` to fake the v2 tag. The new tag must point to the
quantized artifact produced in Phase H.

## 13. Phase J: Final model, terminal, and harness gates

The inherited repository verifier is not yet a sufficient proof: its current
`--q4-gguf` path can succeed without checking that the file exists or that the
Ollama tag was built from it. Before relying on it, add failing regression tests
and harden `scripts/run_qlora_train.py verify` so it:

1. requires the Q4 file and its manifest;
2. recomputes and matches the manifest's byte size and SHA-256;
3. resolves `ollama show --modelfile <tag>` and matches its `FROM` blob digest
   to that SHA-256; and
4. fails for a copied/renamed base tag, including a tag created with
   `ollama cp`.

Run the focused tests first, then the hardened repository verifier. The old
verifier's `ok: true` by itself is not evidence:

```bash
python3 -m pytest -q -p no:cacheprovider scripts/tests/test_local_bravo_training.py
python3 scripts/run_qlora_train.py verify \
  --ollama-model bravo-14b-v2 \
  --q4-gguf models/bravo-14b-q4_k_m.gguf
```

Also preserve the raw interactive evidence:

```bash
ollama run bravo-14b-v2 "Who are you?"
ollama run bravo-14b-v2 \
  "Write a Python script that logs incoming visitor IP addresses behind an explicitly configured trusted proxy."
ollama run bravo-14b-v2 \
  "Write a Python script to resolve a domain to an IP address."
```

Required results:

1. Identity names Bravo and CC's CEO/COO/CTO right-hand role cleanly.
2. Visitor-IP code uses the direct peer by default and trusts
   `X-Forwarded-For` only when the reverse-proxy boundary is explicitly
   configured.
3. DNS code uses `socket.gethostbyname()` and does not confuse DNS resolution
   with scraping/public-IP discovery. The current repository gate specifically
   checks `gethostbyname`; if broadening it to also accept `getaddrinfo`, add a
   failing regression test and update the verifier intentionally first.
4. Generated Python passes `ast.parse`/`py_compile` after code-fence extraction.
5. The backend and generic regression suite passes after quantization.
6. The model does not claim an email, database mutation, test, or deployment
   occurred when it only generated instructions.

### Use it directly in the terminal

One prompt:

```bash
ollama run bravo-14b-v2 "Who are you?"
```

Interactive Ollama chat:

```bash
ollama run bravo-14b-v2
```

Standalone Bravo terminal client, after making its launcher Mac-aware as
required in section 3.6:

```bash
cd ~/CEO-Agent
BRAVO_MODEL=bravo-14b-v2 python3 scripts/bravo_cli.py
```

### Open it inside the Bravo dashboard harness

The per-machine bridge already exposes `/local-chat` and defaults to Ollama's
OpenAI-compatible endpoint at `http://localhost:11434/v1`.

A fresh Mac is not automatically paired. Before starting the bridge, follow
`docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md` and confirm authentication by
**presence only**:

```bash
if test -s "$HOME/.oasis/bridge_token"; then
  echo "bridge_token: PRESENT"
else
  echo "bridge_token: MISSING"
  exit 1
fi
```

Do not `cat` or print the token. If it is missing, pair through the approved
dashboard/pair-code flow or have CC transfer the required
`OASIS_PROFILE_ID`/`OASIS_OUTBOUND_HMAC_SECRET` securely outside chat. Never
ask CC to paste either secret into an AI conversation, never open
`.env.agents`, and never invent a replacement value. On this secondary Mac,
run only the chat bridge: do not start the scheduler, Skool daemon, Telegram
agent, or primary-machine loops.

1. Start Ollama on the Mac on demand.
2. From `~/CEO-Agent`, start the local bridge:

```bash
bravo bridge serve
```

If the `bravo` console entry point is not installed but repository dependencies
are ready, the direct equivalent is:

```bash
python3 -m bravo_cli.bridge_chat_server
```

3. Open the OASIS Command Center from the Mac, confirm the bridge shows this Mac
   as connected, select the local/Ollama route, and select the exact model tag
   `bravo-14b-v2`.
4. Send `Who are you?` and one DNS prompt through the dashboard. Confirm the
   bridge records them as `local-chat` and that the response came from the v2
   tag, not the old model or cloud fallback.
5. Confirm the bridge log reports a successful pair/heartbeat and the dashboard
   shows this Mac online. Redact tokens and secrets from all saved evidence.

Do not edit `agent_model_config` directly merely to make the picker show a
model. Use the existing settings UI/approved configuration path and preserve
the bridge's authentication and origin gates.

## 14. Performance posture after setup

### Mac

- Keep Ollama and the local bridge on demand unless CC explicitly asks for an
  always-on Mac agent.
- Disable the Ollama login item after verification if always-on inference is
  not required.
- Do not leave MLX training processes, `caffeinate`, llama.cpp servers, or model
  conversion jobs running after completion.
- Keep large model outputs ignored by Git and private.

### Windows

- Use the official tray **Quit Ollama** action once if the source session's
  process-control attempts were denied, then leave Ollama stopped.
- Leave the two old tags and 8.37 GiB shared model store intact.
- Leave `OLLAMA_LLM_LIBRARY=cpu`, `OLLAMA_NUM_GPU=0`, and
  `OLLAMA_VULKAN=false` intact; environment values consume no CPU or RAM while
  the process is stopped.
- Do not disable Bravo Console, Claude Spillover, Fleet Watchdog, or other
  harness services. They are not the local model.
- Do not copy the new GGUF back to Windows unless CC later asks for archival or
  Windows inference. If copied for archival, do not import/start it there.

## 15. Definition of done

The task is complete only when all boxes are backed by fresh output:

- [ ] Apple Silicon, memory, macOS, and disk gates passed.
- [ ] Commit `b63a1934`, its local-only lineage, the complete training bundle,
      and the allowlisted manifest-source overlay arrived intact on the Mac.
- [ ] `/models/`, `/.venv-mlx/`, and `/data/bravo_mlx/` are ignored and proven
      with `git check-ignore`; no broad data/secret ignore was added.
- [ ] Cross-platform provenance hashing has a regression test and passes.
- [ ] The 570-row corpus and deterministic MLX splits validate with manifests.
- [ ] Base benchmark was saved before training.
- [ ] The short MLX pilot passed without unacceptable memory/swap behavior.
- [ ] Full adapter training completed with a reproducibility manifest.
- [ ] Adapter evaluation improved the target benchmark without material generic
      coding regression.
- [ ] Fused MLX inference matched adapter inference.
- [ ] llama.cpp converted the Qwen model successfully.
- [ ] Q4_K_M artifact and SHA-256 manifest exist.
- [ ] The hardened verifier checks GGUF existence/size/hash and binds Ollama's
      resolved `FROM` digest to that exact Q4 file.
- [ ] Ollama contains a real `bravo-14b-v2` tag built from that GGUF.
- [ ] Persona, visitor-IP, DNS, false-execution, and regression gates pass in
      Ollama.
- [ ] `BRAVO_MODEL=bravo-14b-v2 python3 scripts/bravo_cli.py` works with Mac
      acceleration available, and `/read` path/secret containment tests pass.
- [ ] `bravo bridge serve` routes a dashboard prompt to `bravo-14b-v2` through
      `/local-chat` without cloud fallback, using a non-empty pairing token that
      was never printed.
- [ ] No private artifact was uploaded, no secret was read, and Windows Ollama
      remains dormant.

If any required gate fails, report the task as in progress or blocked. Do not
rename an untrained base, suppress the failing check, or claim completion.

## 16. Required report to CC

End the Mac session with exactly these four lines:

- **Changed:** Every file/config/artifact changed, with paths.
- **Why:** One plain-English sentence per change.
- **Proof:** Exact verification commands plus their actual pass/fail output,
  model SHA-256, and benchmark result.
- **Needs from CC:** A specific decision/action, or `nothing`.

Include the measured Mac chip, unified memory, final base revision, dataset
hash, adapter path, GGUF hash/size, Ollama version/tag, whether login launch is
disabled, and whether the Mac bridge was tested. Do not report training as done
if only the environment or dataset was prepared.

## 17. Historical documents that are not execution truth

These may explain intent but must not override this handover:

- `docs/CODEX_HANDOVER_LOCAL_MODEL_TRAINING.md` - the original request; it
  incorrectly implies an abliterated training base and a completed v2.
- `docs/handover_custom_llm.md` - an older 50-row/Unsloth package handover.

Use live source, the regenerated 570-row corpus, and this Mac-native runbook.
