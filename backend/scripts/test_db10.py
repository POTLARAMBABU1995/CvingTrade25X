import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.sector_resolver_service import get_custom_sector_candidates

try:
    candidates = get_custom_sector_candidates('AGRICULTURE')
    print("Candidates for AGRICULTURE:", candidates)
except Exception as e:
    print("Error:", e)
