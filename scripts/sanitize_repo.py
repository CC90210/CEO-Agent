import os
import shutil
import argparse
from pathlib import Path

def sanitize_repo(source_dir, output_dir):
    """
    Clones the repository to a new directory and strips personal information/logs.
    Creates a 'Lite' version of the Business-Empire-Agent.
    """
    source_path = Path(source_dir).resolve()
    output_path = Path(output_dir).resolve()

    if output_path.exists():
        print(f"ERROR: Output directory {output_path} already exists. Please choose a different path.")
        return

    # List of files and directories to STRIP (Personal Sauce)
    STRIP_LIST = [
        ".git",                   # Remove full git history
        ".env.agents",            # Private keys
        "brain/SOUL.md",           # Private identity
        "brain/STATE.md",          # Private state
        "brain/USER.md",           # Private user info
        "brain/PROPOSAL_FOR_BENNETT.md", # Specific business plan
        "brain/BENNETT_PLAN.md",         # Specific business plan
        "memory/SESSION_LOG.md",   # Private logs
        "memory/MISTAKES.md",      # Private logs
        "memory/SELF_REFLECTIONS.md", # Private logs
        "memory/ARCHIVES",         # Private logs
        "memory/daily",            # Private daily logs
        "memory/outreach_archive", # Private leads
        "memory/content",          # Private content
        "docs/Cedarwood_ROI_Analysis.md", # Private leads
        "tmp",                     # Temp files
        "node_modules",            # Build artifacts
        ".venv",                   # Build artifacts
        "scripts/archive",         # Obsolete scripts
        "scripts/__pycache__",     # Build artifacts
        ".playwright-mcp",         # Build artifacts
    ]

    # Files to CLEAR (Keep as empty or template)
    CLEAR_LIST = [
        "memory/ACTIVE_TASKS.md",
        "memory/DECISIONS.md",
        "memory/PATTERNS.md",
    ]

    print(f"Creating Lite repository at: {output_path}")
    
    # 1. Copy everything
    shutil.copytree(source_path, output_path, ignore=shutil.ignore_patterns(*STRIP_LIST))

    # 2. Re-create striped directories but keep them empty if needed
    (output_path / "tmp").mkdir(exist_ok=True)
    (output_path / "media/raw").mkdir(parents=True, exist_ok=True)
    (output_path / "media/exports").mkdir(parents=True, exist_ok=True)

    # 3. Clear content of specific files to make them templates
    for file_path in CLEAR_LIST:
        full_path = output_path / file_path
        if full_path.exists():
            with open(full_path, "w") as f:
                f.write(f"# {file_path.split('/')[-1].replace('.md', '').replace('_', ' ')}\n\n(Template: Input your data here)\n")

    # 4. Final Sanity Check for API Keys
    print("Running final security check...")
    for root, dirs, files in os.walk(output_path):
        for file in files:
            if file.endswith((".js", ".py", ".md", ".json", ".txt")):
                file_p = Path(root) / file
                with open(file_p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if "STRIPE_" in content and "_KEY" in content:
                        if "your_key_here" not in content and ".env.agents.template" not in file:
                            print(f"WARNING: Potential hardcoded key in {file_p}")

    print("\nSUCCESS: BEA-Lite repository created.")
    print(f"Path: {output_path}")
    print("You can now initialize a new git repo and push to a public GitHub repository.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BEA Sanitizer - Create a Lite version of the repository.")
    parser.add_argument("--output", "-o", default="../BEA_LITE", help="Output directory path (outside main repo)")
    args = parser.parse_args()
    
    source_dir = Path(__file__).resolve().parent.parent
    sanitize_repo(source_dir, args.output)
