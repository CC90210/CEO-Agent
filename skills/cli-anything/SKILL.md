---
name: cli-anything
description: Generate agent-native CLI wrappers for any software, API, or service. Use when MCP servers are unreliable or when a tool needs a CLI interface for agent automation.
triggers: [CLI, wrapper, SDK, subprocess, CLI-anything, agent-native CLI]
tier: specialized
dependencies: [security-protocol]
---

# CLI-Anything — Universal CLI Generation

## Overview

Transform any GUI application, API, or service into a structured, agent-friendly command-line interface. CLIs are more reliable than MCP servers and provide universal access across all agent interfaces (Claude Code, Gemini CLI, Anti-Gravity, Telegram).

**Core Principle:** CLI is the universal interface for both humans and AI agents. When an MCP breaks, a CLI still works.

**Based on:** [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology, adapted for Business-Empire-Agent.

## When to Use

- MCP server for a tool is broken or unreliable
- Need to wrap a GUI application for agent control
- Need a universal tool interface that works across all AI platforms
- Building a new integration that should work without MCP dependency
- Want to make any software "agent-native"

## The 7-Phase Pipeline

### Phase 1: Codebase/API Analysis

**Input:** Target software source code, API docs, or service documentation.

**Actions:**
1. Map GUI operations or API endpoints to underlying functions
2. Catalog the backend engine, data model, and file formats
3. Identify which operations are read-only (probes) vs. mutations
4. Document authentication, state management, and output formats

**Output:** Architecture analysis document.

**Template prompt:**
```
Analyze [SOFTWARE/API] and produce:
1. Core operations list (grouped by domain)
2. Data model (input/output formats)
3. Authentication method
4. State management approach
5. Dependencies and system requirements
```

### Phase 2: CLI Architecture Design

**Input:** Analysis from Phase 1.

**Design decisions:**
- **Interaction model:** Subcommand-only (stateless) or REPL (stateful) or both
- **Command groups:** Match the software's natural domains
- **Output format:** Always support both JSON (for agents) and human-readable
- **State model:** How to persist state between invocations

**Output:** CLI design specification.

**Key rules:**
- Every command must have `--json` flag for machine-readable output
- Group commands logically: `project`, `export`, `query`, etc.
- Include `--help` at every level
- Use Click framework for Python CLIs

### Phase 3: Implementation

**Critical Rule:** The backend MUST invoke the actual software via subprocess. NEVER reimplement rendering, processing, or core logic in Python.

**Architecture:**
```
cli_anything/
└── <software>/
    ├── <software>_cli.py     # Main CLI entry point (Click groups)
    ├── core/
    │   ├── project.py        # Project/session state management
    │   ├── export.py         # File generation/export via real software
    │   └── session.py        # Undo/redo via deep-copy snapshots
    ├── utils/
    │   ├── backend.py        # Subprocess calls to real software
    │   └── repl_skin.py      # Unified REPL interface (copy from templates)
    └── tests/
        ├── test_core.py      # Unit tests (synthetic data)
        └── test_e2e.py       # E2E tests (invoke real software)
```

**Backend Pattern:**
```python
import subprocess
import json

def invoke_software(command: str, args: list[str], timeout: int = 30) -> dict:
    """Call the real software via subprocess."""
    result = subprocess.run(
        [command] + args,
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip(), "code": result.returncode}
    return {"output": result.stdout.strip(), "code": 0}
```

**CLI Entry Point Pattern:**
```python
import click
import json as json_lib

@click.group()
@click.option('--json', 'output_json', is_flag=True, help='JSON output for agents')
@click.pass_context
def cli(ctx, output_json):
    ctx.ensure_object(dict)
    ctx.obj['json'] = output_json

@cli.command()
@click.argument('query')
@click.pass_context
def search(ctx, query):
    """Search for items."""
    result = backend.search(query)
    if ctx.obj['json']:
        click.echo(json_lib.dumps(result))
    else:
        for item in result:
            click.echo(f"  {item['name']}: {item['value']}")

if __name__ == '__main__':
    cli()
```

### Phase 4: Test Planning

Before writing tests, document:
1. Unit test inventory (synthetic data, no real software needed)
2. E2E test inventory (invoke real software, produce real artifacts)
3. Edge cases (missing software, bad input, timeouts)

### Phase 5: Test Implementation

**Unit tests:** Use synthetic data, mock subprocess calls.
**E2E tests:** MUST invoke real software and verify output artifacts exist and are valid.

```python
def test_export_produces_valid_file(tmp_path):
    """E2E: Real software must produce a real output file."""
    output = tmp_path / "output.pdf"
    result = export_document(input_file, str(output))
    assert output.exists()
    assert output.stat().st_size > 0
    # Verify magic bytes for file type
    with open(output, 'rb') as f:
        assert f.read(4) == b'%PDF'
```

### Phase 6: Packaging

**setup.py template:**
```python
from setuptools import find_namespace_packages, setup

setup(
    name="cli-anything-<software>",
    version="1.0.0",
    packages=find_namespace_packages(),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-<software>=cli_anything.<software>.<software>_cli:main",
        ],
    },
    python_requires=">=3.10",
)
```

**Install locally:**
```bash
cd agent-harness
pip install -e .
cli-anything-<software> --help
```

### Phase 7: Integration

After the CLI is built and tested:
1. Add to `scripts/` or install globally via pip
2. Update `brain/CAPABILITIES.md` with new tool
3. Add usage examples to relevant skill docs
4. Update all AI entry points if needed (CLAUDE.md, GEMINI.md, ANTIGRAVITY.md)

## Reusable Components

### ReplSkin (Unified REPL Interface)
Copy from `scripts/cli_templates/repl_skin.py`. Provides:
- Consistent terminal styling across all CLIs
- `success()`, `error()`, `warning()`, `info()` message types
- Table display with box-drawing characters
- Built on `prompt_toolkit` for rich terminal editing
- `NO_COLOR` environment variable support

### Backend Module Pattern
Copy from `scripts/cli_templates/backend_template.py`. Provides:
- Subprocess wrapper with timeout and error handling
- JSON output parsing
- Retry logic for flaky tools
- Cross-platform path resolution (Windows + Unix)

## Priority CLI Candidates

When deciding what to wrap next, prioritize:

| Priority | Target | Why |
|----------|--------|-----|
| **HIGH** | Tools with broken MCPs | Direct replacement, immediate value |
| **HIGH** | Frequently used APIs without MCPs | Reduce manual curl/fetch usage |
| **MEDIUM** | GUI apps used in content pipeline | FFmpeg, Whisper, ElevenLabs already wrapped |
| **LOW** | Tools with working MCPs | Only if MCP becomes unreliable |

## Existing CLI Wrappers (Already Built)

These follow the CLI-Anything pattern already:
- `scripts/integrations/supabase_tool.py` — Supabase SDK wrapper (3 projects)
- `scripts/integrations/stripe_tool.py` — Stripe API wrapper (balance, customers, invoices)
- `../CMO-Agent/scripts/late_tool.py` (owned by Maven) — Zernio (formerly Late) social-scheduling wrapper
- `scripts/integrations/firecrawl_tool.py` — Firecrawl scrape/extract wrapper
- `scripts/integrations/google_tool.py` — Google Workspace (gws CLI + SMTP fallback) wrapper
- `../CMO-Agent/scripts/edit_content_v2.py` — FFmpeg + Whisper video pipeline (relocated to Maven 2026-04-04)

## Anti-Patterns

1. **Never reimplement core logic** — Always call real software via subprocess
2. **Never skip JSON output** — Agents need machine-readable output
3. **Never hardcode credentials** — Read from `.env.agents` or environment
4. **Never skip E2E tests** — Unit tests alone don't prove the CLI works with real software
5. **Never install into Business-Empire-Agent** — CLIs go in separate dirs or global pip

## Quick Start

When CC says "make a CLI for X":

1. Run Phase 1: Analyze the target (read docs, explore API)
2. Run Phase 2: Design commands (present to CC for approval)
3. Run Phase 3-6: Build, test, package
4. Run Phase 7: Integrate into agent ecosystem
5. Log to `memory/SESSION_LOG.md`

## Reference

- Original methodology: [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything)
- ReplSkin template: `scripts/cli_templates/repl_skin.py`
- Backend template: `scripts/cli_templates/backend_template.py`
- Setup template: `scripts/cli_templates/setup_template.py`

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
