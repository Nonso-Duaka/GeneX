"""Vercel Python entrypoint.

Vercel auto-detects this file as a serverless function and serves the
exported `app` (an ASGI FastAPI instance). Static files in /public are
served directly by Vercel's CDN, not by this function.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app  # noqa: E402, F401
