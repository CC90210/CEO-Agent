---
tags: [docs]
last_updated: 2026-07-27
---

# Handover & Audit Specification: Custom LLM Fine-Tuning & API Serving Package

> **Notice for Reviewing AI Agents (Codex / Gemini / Claude / OpenCode):**
> This document serves as the complete technical handover and code-review specification for the newly implemented Custom LLM package in `Business-Empire-Agent`. Use this guide to review implementation quality, verify data formatting, check error bounds, and test integration points.

---

## 1. System Mission & Context

This package enables `Business-Empire-Agent` (Bravo) to train, serve, and query an uncensored, custom open-weights LLM (e.g. Qwen 2.5 14B / 32B or DeepSeek Distill). The fine-tuned model is trained specifically on workspace context (`AGENTS.md`, `CLAUDE.md`, `brain/SOUL.md`), CLI tool execution conventions (`scripts/`), and plain-English founder communication style.

---

## 2. File & Component Registry

| File Path | Purpose | Language / Tech | Primary Dependencies |
| :--- | :--- | :--- | :--- |
| [`scripts/llm_training/generate_dataset.py`](file:///c:/Users/User/Business-Empire-Agent/scripts/llm_training/generate_dataset.py) | Generates and validates ChatML SFT JSONL training datasets. | Python 3.12 | `json`, `argparse`, `lib.claude_cli` |
| [`scripts/llm_training/train_unsloth.py`](file:///c:/Users/User/Business-Empire-Agent/scripts/llm_training/train_unsloth.py) | QLoRA fine-tuning runner for Linux GPU pods (RunPod/Vast.ai). | Python 3.12 | `unsloth`, `trl`, `transformers`, `datasets` |
| [`scripts/llm_training/litellm_config.yaml`](file:///c:/Users/User/Business-Empire-Agent/scripts/llm_training/litellm_config.yaml) | OpenAI-compatible proxy config with master/custom API key enforcement. | YAML | `litellm` |
| [`scripts/llm_training/deploy_server.sh`](file:///c:/Users/User/Business-Empire-Agent/scripts/llm_training/deploy_server.sh) | Automated Linux deployment script for Ollama + LiteLLM. | Bash | `ollama`, `litellm`, `curl` |
| [`scripts/lib/custom_llm_client.py`](file:///c:/Users/User/Business-Empire-Agent/scripts/lib/custom_llm_client.py) | Workspace integration library for querying the custom LLM server endpoint. | Python 3.12 | `urllib.request`, `json`, `os` |

---

## 3. Data Flow & Integration Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. DATASET GENERATION                                                                        │
│  - Input: System rules (AGENTS.md, SOUL.md), CLI schemas, seed scenarios.                   │
│  - Processing: Formatted into ChatML schema (<|im_start|>role\ncontent<|im_end|>).          │
│  - Output: `data/training/bravo_harness_sft.jsonl`                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. QLORA FINE-TUNING (Unsloth on RunPod / GPU Pod)                                          │
│  - Model: Qwen/Qwen2.5-14B-Instruct-bnb-4bit                                                │
│  - Optimization: 4-bit quantization, LoRA rank r=16, alpha=16, target modules (q,k,v,o,gate).│
│  - Output: LoRA adapters + GGUF export (Q4_K_M)                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. API SERVING & PROXY                                                                      │
│  - Engine: Ollama (local GGUF host) + LiteLLM Proxy (Port 4000)                             │
│  - Security: Bearer Token API Key Authentication (`sk-oasis-...`)                           │
│  - Endpoint: `http://<host>:4000/v1/chat/completions`                                       │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. WORKSPACE HARNESS INTEGRATION                                                            │
│  - Client: `scripts/lib/custom_llm_client.py`                                               │
│  - Environment: `CUSTOM_LLM_BASE_URL` & `CUSTOM_LLM_API_KEY` loaded from `.env.agents`       │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Code Quality & Security Audit Checklist for Reviewer

Please evaluate the codebase against the following criteria:

### A. Data Integrity & Schema Formatting
- [ ] **ChatML Tokens:** Verify that `generate_dataset.py` and `train_unsloth.py` produce exact `<|im_start|>` and `<|im_end|>` tags.
- [ ] **JSONL Syntax:** Confirm each row in `data/training/bravo_harness_sft.jsonl` contains valid `messages` array with `system`, `user`, `assistant` roles.

### B. Security & Credentials
- [ ] **No Hardcoded Secrets in Git:** Verify no production private keys or live credentials are embedded in code files (default keys in configs/examples are clearly marked defaults).
- [ ] **`.env.agents` Isolation:** Confirm `custom_llm_client.py` reads `CUSTOM_LLM_API_KEY` from `.env.agents` or environment overrides.

### C. Cross-Platform Compatibility
- [ ] **Windows Console Output:** Confirm all print statements in Python scripts avoid non-ASCII characters (`[OK]` instead of unicode checkmarks) to prevent `cp1252` encoding errors.
- [ ] **Shell Scripting:** `deploy_server.sh` is tagged for Linux/Bash environment execution (RunPod / server nodes).

### D. Error Handling & Resilience
- [ ] **Graceful Degradation:** `custom_llm_client.py` handles connection timeouts (5s for health check, 60s for inference) gracefully without crashing callers.

---

## 5. Reviewer Verification Commands

Run the following commands to verify the component functionality:

```bash
# 1. Test Dataset Generator and Verification Logic
python scripts/llm_training/generate_dataset.py --count 20 --output data/training/test_sft.jsonl
python scripts/llm_training/generate_dataset.py --verify data/training/test_sft.jsonl

# 2. Test Custom LLM Client Library Interface
python scripts/lib/custom_llm_client.py --help
python scripts/lib/custom_llm_client.py --health

# 3. Verify Code Formatting / Syntax Parsing
python -m py_compile scripts/llm_training/generate_dataset.py
python -m py_compile scripts/llm_training/train_unsloth.py
python -m py_compile scripts/lib/custom_llm_client.py
```

---

## 6. Handover Summary & Next Steps

* **Status:** Complete, local unit tests passing.
* **Pending Operator Action:** Rent 1x NVIDIA RTX 4090 on RunPod ($0.44/hr) to execute `train_unsloth.py` for ~45 minutes when fine-tuning is scheduled.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
