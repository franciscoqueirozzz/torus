import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

sys.path.insert(0, str(BACKEND))

from app.api import app