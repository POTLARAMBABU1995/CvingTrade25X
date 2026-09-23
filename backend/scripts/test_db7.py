import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from routes.sector_rotation import _resolve_sector_candidates

app = create_app()

with app.app_context():
    try:
        print("Candidates:", _resolve_sector_candidates('AGRICULTURE'))
    except Exception as e:
        print("Error:", e)
