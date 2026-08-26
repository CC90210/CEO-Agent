"""Push the OASIS workspace Google Calendar credentials to Vercel Production.

Reads GOOGLE_REFRESH_TOKEN (or BREEZE_GOOGLE_REFRESH_TOKEN) and GMAIL_USER from
.env.agents — never hardcoded — and pipes them via stdin to `vercel env add`
for the three variables the Command Center's workspace-calendar fallback needs:
GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN, GOOGLE_SYSTEM_CALENDAR_ADDRESS,
GOOGLE_CALENDAR_ID. Token values are only ever printed as lengths.
"""
import os, sys, subprocess, dotenv

def main():
    env_path = os.path.join(os.getcwd(), ".env.agents")
    if not os.path.exists(env_path):
        print("ERROR: .env.agents file not found")
        sys.exit(1)
        
    env_vars = dotenv.dotenv_values(env_path)
    refresh_token = env_vars.get("GOOGLE_REFRESH_TOKEN") or env_vars.get("BREEZE_GOOGLE_REFRESH_TOKEN")
    user_email = env_vars.get("GMAIL_USER") or "conaugh@oasisai.work"
    
    if not refresh_token:
        print("ERROR: No GOOGLE_REFRESH_TOKEN found in .env.agents")
        sys.exit(1)
        
    print(f"Loaded credentials for user: {user_email}")
    print(f"Refresh token length: {len(refresh_token)} chars")
    
    app_dir = os.path.abspath(os.path.join(os.getcwd(), "..", "APPS", "oasis-command-center"))
    if not os.path.exists(app_dir):
        print(f"ERROR: App dir not found at {app_dir}")
        sys.exit(1)

    targets = [
        ("GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN", refresh_token),
        ("GOOGLE_SYSTEM_CALENDAR_ADDRESS", user_email),
        ("GOOGLE_CALENDAR_ID", "primary")
    ]
    
    for key, val in targets:
        print(f"Adding {key} to Vercel (production)...")
        # vercel env add <key> production
        proc = subprocess.Popen(
            f'vercel env add {key} production',
            cwd=app_dir,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=val + "\n")
        print(f"  Result code: {proc.returncode}")
        if proc.returncode != 0:
            print(f"  Stderr: {stderr}")
            print(f"  Stdout: {stdout}")
        else:
            print(f"  Successfully added {key}!")

if __name__ == "__main__":
    main()
