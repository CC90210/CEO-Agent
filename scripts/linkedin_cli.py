import os
import sys
import json
import click
from dotenv import load_dotenv
from linkedin_api import Linkedin

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.agents'))

def get_client():
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")
    if not email or not password:
        click.echo(json.dumps({"error": "LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env.agents"}), err=True)
        sys.exit(1)
    
    try:
        # The linkedin-api automatically caches the session cookies in ~/.linkedin_api/
        # so it doesn't need to log in fresh every time after the first success.
        api = Linkedin(email, password)
        return api
    except Exception as e:
        click.echo(json.dumps({"error": f"Authentication failed: {str(e)}"}), err=True)
        sys.exit(1)

@click.group()
def cli():
    """CLI-Anything wrapper for LinkedIn Automation (Voyager API)."""
    pass

@cli.command()
def verify():
    """Verify authentication and print the logged-in user's profile."""
    api = get_client()
    try:
        profile = api.get_user_profile()
        name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
        click.echo(json.dumps({"status": "success", "user": name}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))

@cli.command()
@click.argument('username') # The part of the URL after /in/
@click.option('--message', '-m', default=None, help="Personalized connection message.")
def connect(username, message):
    """Send a connection request to a user profile by their public username."""
    api = get_client()
    try:
        # Get profile URN needed for the connection request
        profile = api.get_user_profile(username)
        if not profile:
            click.echo(json.dumps({"error": f"Profile '{username}' not found."}))
            return
            
        profile_urn_id = profile.get("profile_id")
        
        # Send request
        res = api.add_connection(profile_urn_id, message=message)
        
        # The API returns a boolean or an empty string on success usually
        click.echo(json.dumps({"status": "success", "result": res}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))

@cli.command()
@click.argument('username')
@click.argument('message')
def message(username, message):
    """Send a direct message to a 1st degree connection."""
    api = get_client()
    try:
        profile = api.get_user_profile(username)
        if not profile:
            click.echo(json.dumps({"error": f"Profile '{username}' not found."}))
            return
            
        urn_id = profile.get("profile_id")
        res = api.send_message(message, recipients=[urn_id])
        click.echo(json.dumps({"status": "success", "result": res}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))

if __name__ == '__main__':
    cli()
