"""Central configuration and shared constants for the AgriTrial MVP.

Everything that more than one module needs (paths, role names, dropdown lists)
lives here so the phone app, the API and the tests all agree.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Runtime settings (override with a .env file, see .env.example) ---------
API_URL = os.getenv("AGRITRIAL_API_URL", "http://127.0.0.1:8000")
DB_PATH = os.getenv("AGRITRIAL_DB", str(BASE_DIR / "agritrial.db"))
CLOUD_MOCK_DB = os.getenv("AGRITRIAL_CLOUD_MOCK_DB", str(BASE_DIR / "cloud_mock.db"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
# Service key stays on the API side ONLY. Never put it in the phone app.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# --- Roles (names match Milestone 1) ----------------------------------------
ROLE_FARMER = "Small Farmer"
ROLE_DALRRD = "DALRRD Regulatory Official"
ROLE_UWC = "UWC Researcher"
ALL_ROLES = (ROLE_FARMER, ROLE_DALRRD, ROLE_UWC)
STAKEHOLDER_ROLES = (ROLE_DALRRD, ROLE_UWC)

# --- Dropdown lists ----------------------------------------------------------
# Temporary staging options until the Eduponics research team confirms them.
SITES = ("SITE-WINELANDS-01",)
ENVIRONMENTS = ("Greenhouse", "Aquaponics", "Open Field")
CROPS = ("Tomato", "Lettuce", "Maize")
TREATMENT_GROUPS = tuple(f"TGID-{i}" for i in range(6))  # TGID-0 = Control
VARIANT_GROUPS = TREATMENT_GROUPS[1:]
VISIT_TYPES = ("ROUTINE_MONITORING", "HARVEST_VISIT")
LANGUAGES = ("English", "Afrikaans", "isiXhosa")

# Minimum number of non-blank nitrate readings per group for a 95% CI.
MIN_N = 5
