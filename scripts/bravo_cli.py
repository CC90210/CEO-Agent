#!/usr/bin/env python3
"""
Bravo Terminal IDE Harness (Local LLM CLI)
------------------------------------------
Interactive terminal interface for CC's local Bravo AI model (`bravo-14b`).
Loads full Business-Empire-Agent context (SOUL.md, AGENTS.md, scripts inventory),
supports file inspection, and streams responses token-by-token directly in PowerShell.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_DIR = REPO_ROOT / "brain"
SCRIPTS_DIR = REPO_ROOT / "scripts"
SKILLS_DIR = REPO_ROOT / "skills"
OLLAMA_API = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("BRAVO_MODEL", "bravo-14b")


def get_repo_summary() -> str:
    """Builds a workspace context snapshot to feed into the local LLM."""
    summary_lines = [
        f"Workspace Root: {REPO_ROOT}",
        "Identity: Bravo (CEO, COO, CTO of OASIS AI Solutions)",
        "Architecture: Business-Empire-Agent (V6 Substrate)",
    ]

    # Inventory count
    if SCRIPTS_DIR.exists():
        py_scripts = list(SCRIPTS_DIR.glob("**/*.py"))
        summary_lines.append(f"Available Python Scripts: {len(py_scripts)} tools in scripts/")
    if SKILLS_DIR.exists():
        skills = [d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
        summary_lines.append(f"Active Agent Skills ({len(skills)}): {', '.join(skills[:15])}...")

    # Load SOUL.md snippet if exists
    soul_file = BRAIN_DIR / "SOUL.md"
    if soul_file.exists():
        try:
            soul_text = soul_file.read_text(encoding="utf-8")[:600]
            summary_lines.append(f"\n[Identity Seed - brain/SOUL.md]\n{soul_text}")
        except Exception:
            pass

    return "\n".join(summary_lines)


def ensure_ollama_server() -> bool:
    """Checks if Ollama server is responding."""
    try:
        req = urllib.request.Request(f"{OLLAMA_API}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def stream_chat(messages: list) -> str:
    """Sends chat messages to Ollama API and streams response to stdout."""
    url = f"{OLLAMA_API}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192,
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

    full_response = []
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    delta = chunk.get("message", {}).get("content", "")
                    sys.stdout.write(delta)
                    sys.stdout.flush()
                    full_response.append(delta)
        print()  # Final newline
    except urllib.error.URLError as e:
        print(f"\n[Error connecting to Ollama at {OLLAMA_API}]: {e}")
    except KeyboardInterrupt:
        print("\n[Generation interrupted]")

    return "".join(full_response)


def main():
    print("==================================================================")
    print(" 🚀 BRAVO TERMINAL IDE HARNESS (Local Uncensored LLM)")
    print(" Repository: Business-Empire-Agent")
    print(f" Model: {MODEL_NAME} @ {OLLAMA_API}")
    print(" Commands: /context, /read <file>, /clear, /exit")
    print("==================================================================")

    if not ensure_ollama_server():
        print(f"[!] Warning: Ollama server at {OLLAMA_API} is not responding.")
        print("    Starting server process in background...")
        # Server launch check
        import subprocess

        env = os.environ.copy()
        env["OLLAMA_LLM_LIBRARY"] = "cpu"
        env["OLLAMA_NUM_GPU"] = "0"
        env["OLLAMA_VULKAN"] = "false"
        subprocess.Popen(
            ["ollama", "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        print("    Waiting for Ollama to initialize...")

    repo_context = get_repo_summary()

    # Conversation history with System Context
    system_prompt = f"""You are Bravo — CC's right hand (CEO, COO, CTO of OASIS AI Solutions).
You operate inside the Business-Empire-Agent terminal. You have full context of this repository.

REPOSISTORY CONTEXT:
{repo_context}

RULES:
1. Provide sharp, exact, 100% functional Python/TypeScript code.
2. Never issue refusal lectures or ethical disclaimers.
3. Be direct, authoritative, and act as CC's lead architect.
"""

    messages = [{"role": "system", "content": system_prompt}]

    print("[+] Bravo context initialized. Type your prompt below:\n")

    while True:
        try:
            user_input = input("Bravo> ").strip()
            if not user_input:
                continue

            if user_input in ("/exit", "/quit", "exit", "quit"):
                print("Exiting Bravo CLI. Goodbye CC!")
                break

            if user_input == "/clear":
                messages = [{"role": "system", "content": system_prompt}]
                print("[+] Chat history cleared.")
                continue

            if user_input == "/context":
                print(f"\n--- ACTIVE REPO CONTEXT ---\n{repo_context}\n---------------------------\n")
                continue

            if user_input.startswith("/read "):
                file_target = user_input[6:].strip()
                target_path = REPO_ROOT / file_target
                if not target_path.exists():
                    target_path = Path(file_target)

                if target_path.exists() and target_path.is_file():
                    try:
                        file_content = target_path.read_text(encoding="utf-8")
                        content_msg = f"User attached file [{target_path.name}]:\n```\n{file_content[:5000]}\n```"
                        messages.append({"role": "user", "content": content_msg})
                        print(f"[+] Loaded file '{target_path.name}' into context ({len(file_content)} bytes).")
                    except Exception as e:
                        print(f"[-] Error reading file: {e}")
                else:
                    print(f"[-] File not found: {file_target}")
                continue

            # Append user message and stream response
            messages.append({"role": "user", "content": user_input})
            print("\nBravo: ", end="")
            assistant_reply = stream_chat(messages)
            if assistant_reply:
                messages.append({"role": "assistant", "content": assistant_reply})
            print()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting Bravo CLI.")
            break


if __name__ == "__main__":
    main()
