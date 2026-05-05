"""Shared runtime constants for the bravo_cli + scripts surfaces.

Centralizes the few values that were drifting across multiple files.
Anything more complex than a string belongs in its own module.
"""

import os


def dashboard_url() -> str:
    """Resolve the OASIS dashboard base URL.

    Order of precedence:
      1. BRAVO_DASHBOARD_URL env var (set explicitly by an operator or CI)
      2. Hardcoded default — the production Vercel deployment

    Returned without a trailing slash.
    """
    return (os.environ.get("BRAVO_DASHBOARD_URL")
            or "https://agent-dashboard-cc90210.vercel.app").rstrip("/")
