import os
import requests
import json
import subprocess
from pathlib import Path

def create_github_repo():
    # 1. Load the token from .env.agents
    env_path = Path(".env.agents").resolve()
    if not env_path.exists():
        print("ERROR: .env.agents not found.")
        return

    env_vars = {}
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                key, val = line.strip().split("=", 1)
                env_vars[key.strip()] = val.strip()

    token = env_vars.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        print("ERROR: GITHUB_PERSONAL_ACCESS_TOKEN not found in .env.agents")
        return

    # 2. Repo settings
    repo_name = "business-empire-agent-lite"
    description = "The core file structure and orchestration chassis for AI agents. A simplified version of the Business-Empire-Agent."
    username = "CC90210"

    # 3. Create repo via API
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "name": repo_name,
        "description": description,
        "private": False,
        "auto_init": False
    }

    print(f"Creating repository {repo_name} on GitHub...")
    response = requests.post("https://api.github.com/user/repos", headers=headers, json=payload)

    if response.status_code == 201:
        print(f"SUCCESS: Repository created at {response.json()['html_url']}")
    elif response.status_code == 422:
        print(f"WARNING: Repository {repo_name} already exists or has an issue. Continuing with git push...")
    else:
        print(f"ERROR: Failed to create repository. Status code: {response.status_code}")
        print(response.text)
        return

    # 4. Initialize local git and push
    bea_lite_path = Path("C:/Users/User/BEA_LITE").resolve()
    os.chdir(bea_lite_path)

    print("Initializing local repository and pushing to GitHub...")
    commands = [
        ["git", "init"],
        ["git", "add", "."],
        ["git", "commit", "-m", "initial commit: BEA-Lite template deployment"],
        ["git", "branch", "-M", "main"],
        ["git", "remote", "add", "origin", f"https://github.com/{username}/{repo_name}.git"],
        ["git", "push", "-u", "origin", "main", "-f"] # Force push since it's a new repo or we want to overwrite
    ]

    for cmd in commands:
        try:
            # Mask the token if it appears in git push command (not needed here since we use remote add with URL)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"RUN: {' '.join(cmd)}")
        except subprocess.CalledProcessError as e:
            if "remote origin already exists" in str(e.stderr):
                 subprocess.run(["git", "remote", "set-url", "origin", f"https://github.com/{username}/{repo_name}.git"])
                 continue
            print(f"ERROR in command: {' '.join(cmd)}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            break

    print("\nFINAL STATUS: BEA-Lite has been successfully pushed to GitHub.")
    print(f"Link: https://github.com/{username}/{repo_name}")

if __name__ == "__main__":
    create_github_repo()
