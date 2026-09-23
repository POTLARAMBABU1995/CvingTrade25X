import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.sector_hierarchy_service import SectorHierarchyService

try:
    svc = SectorHierarchyService()
    candidates = svc.resolve_candidates('AGRICULTURE')
    print("Candidates for AGRICULTURE:", candidates)
except Exception as e:
    print("Error:", e)
