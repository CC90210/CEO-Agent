# 📋 Codex Handover: Fine-Tuning Local LLM (`bravo-14b`) for Business-Empire-Agent

> **Target Agent:** Codex (Backend Executor / Model Trainer)  
> **Goal:** Train up the local model (`bravo-14b`, based on `Qwen2.5-Coder-14B-Instruct-Abliterated`) using the `Business-Empire-Agent` codebase context, production script patterns, and Bravo identity.

---

## 1. Executive Summary & Context

CC wants the local model (`bravo-14b`) to be fine-tuned so that it achieves higher accuracy for:
1. **Network & Backend Systems Programming**: Proper separation of DNS domain resolution (`socket`), HTTP scrapers, Flask/FastAPI IP logging endpoints (`request.remote_addr` / `X-Forwarded-For`), and rate limiters.
2. **Business-Empire-Agent Native Awareness**: Understanding the 537 python scripts in `scripts/`, 165 agent skills in `skills/`, identity rules in `brain/SOUL.md`, and CLI commands.
3. **Uncensored Execution**: Zero-refusal responses to technical code generation without corporate disclaimer bloat.

---

## 2. Infrastructure Setup & Current State

- **Local Runner:** Ollama v0.34.0 running on Windows CPU mode (`OLLAMA_LLM_LIBRARY=cpu`, `OLLAMA_NUM_GPU=0`, `OLLAMA_VULKAN=false`).
- **Installed Model Tag:** `bravo-14b` (compiled from [config/ollama/Modelfile.bravo-14b](file:///c:/Users/User/Business-Empire-Agent/config/ollama/Modelfile.bravo-14b)).
- **Terminal CLI:** [scripts/bravo_cli.py](file:///c:/Users/User/Business-Empire-Agent/scripts/bravo_cli.py) & [bravo.ps1](file:///c:/Users/User/Business-Empire-Agent/bravo.ps1).
- **Dataset Generator Script:** [scripts/train_local_bravo.py](file:///c:/Users/User/Business-Empire-Agent/scripts/train_local_bravo.py).
- **Dataset Path:** `data/bravo_dataset.jsonl`.

---

## 3. Step-by-Step Training Protocol for Codex

Codex should execute the following 4 phases to produce `bravo-14b-v2`:

### Phase 1: Expand the Training Dataset (`data/bravo_dataset.jsonl`)
Modify `scripts/train_local_bravo.py` to automatically mine instruction-response pairs from:
- `scripts/integrations/*.py` (Stripe, Supabase, Google, n8n, Wrangler, Send Gateway).
- `skills/*/SKILL.md` (Workflow and tool invocation rules).
- `brain/SOUL.md` & `AGENTS.md` (Bravo persona, voice, rules).
- Complex coding patterns (DNS resolution, Flask/FastAPI IP loggers, rate limiters, async webhooks, JWT authentication, SQLite/Turso queries).

Ensure all dataset items follow OpenAI/Qwen ChatML format:
```json
{
  "messages": [
    {"role": "system", "content": "You are Bravo — CC's right hand: CEO, COO, and CTO of OASIS AI Solutions in one."},
    {"role": "user", "content": "<Instruction>"},
    {"role": "assistant", "content": "<Functional, complete Python/TypeScript code>"}
  ]
}
```

### Phase 2: Run QLoRA Fine-Tuning
Execute `scripts/run_qlora_train.py` using PyTorch + Hugging Face `peft` + `trl` on `Qwen/Qwen2.5-Coder-14B-Instruct` (or Unsloth for 2x faster GPU fine-tuning if GPU/Colab is available):

```bash
python scripts/run_qlora_train.py
```

Target Hyperparameters:
- **Base Model:** `Qwen/Qwen2.5-Coder-14B-Instruct`
- **LoRA Rank (r):** 16, `lora_alpha`: 32
- **Target Modules:** `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`
- **Max Sequence Length:** 2048
- **Learning Rate:** 2e-4 (Cosine schedule)

### Phase 3: Export & Quantize to GGUF
1. Merge LoRA weights into base model using PEFT `merge_and_unload()`.
2. Convert merged Hugging Face model to GGUF format via `llama.cpp`:
   ```bash
   python llama.cpp/convert_hf_to_gguf.py models/bravo-14b-merged --outfile models/bravo-14b-f16.gguf
   ```
3. Quantize to Q4_K_M (optimal CPU performance & memory footprint ~9.0 GB):
   ```bash
   ./llama-quantize models/bravo-14b-f16.gguf models/bravo-14b-q4_k_m.gguf Q4_K_M
   ```

### Phase 4: Import into Ollama as `bravo-14b-v2`
Update [config/ollama/Modelfile.bravo-14b](file:///c:/Users/User/Business-Empire-Agent/config/ollama/Modelfile.bravo-14b) to point to `models/bravo-14b-q4_k_m.gguf` and re-build:

```powershell
ollama create bravo-14b-v2 -f config/ollama/Modelfile.bravo-14b
```

---

## 4. Verification Gate for Codex

Before marking the training task complete, Codex must verify:
1. `ollama run bravo-14b-v2 "Who are you?"` -> Returns Bravo persona cleanly.
2. `ollama run bravo-14b-v2 "Write a python script that logs incoming visitor IP addresses"` -> Returns valid Flask/FastAPI server with `X-Forwarded-For` logging.
3. `ollama run bravo-14b-v2 "Write a python script to resolve a domain to an IP"` -> Returns valid `socket.gethostbyname()` code.
