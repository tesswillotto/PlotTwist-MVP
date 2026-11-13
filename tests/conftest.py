"""Shared test fixtures. Tests never touch the real databases or Supabase."""
import os
import sys
import tempfile
from pathlib import Path

# Must be set BEFORE the project modules are imported.
_tmp = tempfile.mkdtemp(prefix="agritrial_tests_")
os.environ["AGRITRIAL_DB"] = os.path.join(_tmp, "default_local.db")
os.environ["AGRITRIAL_CLOUD_MOCK_DB"] = os.path.join(_tmp, "default_cloud.db")
os.environ["AGRITRIAL_NO_BG_SYNC"] = "1"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import cloud_store
import config
import database as db

# config.py calls load_dotenv(), which would bring real Supabase keys back from a local
# .env file. Clear them again so the tests can never reach a real project.
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)
config.SUPABASE_URL = ""
config.SUPABASE_SERVICE_KEY = ""


@pytest.fixture
def local_db(tmp_path):
    """A fresh local (phone) database."""
    path = str(tmp_path / "phone.db")
    db.init_sqlite_db(path)
    return path


@pytest.fixture
def client(tmp_path):
    """The FastAPI app wired to a fresh simulated cloud."""
    cloud_store.set_store(cloud_store.MockCloudStore(str(tmp_path / "cloud.db")))
    import api_engine
    return TestClient(api_engine.app)


@pytest.fixture
def valid_record():
    """A record that passes every rule (use copy + change one field per test)."""
    return {
        "local_id": "11111111-1111-1111-1111-111111111111",
        "created_timestamp": "2026-10-12 08:00:00", "entry_date": "2026-10-12",
        "site_id": "SITE-WINELANDS-01", "environment_id": "Greenhouse", "crop_id": "Tomato",
        "treatment_group_id": "TGID-1",
        "plot_id": "SITE-WINELANDS-01-Tomato-TGID-1", "trial_week": "TW-7",
        "visit_type": "ROUTINE_MONITORING", "observer_id": "OID-102",
        "plant_height_cm": 42.5, "leaf_count": 16, "nitrate_mg_l": 140.0,
        "is_harvest_complete": False,
    }


FARMER = {"X-User-Role": config.ROLE_FARMER}
DALRRD = {"X-User-Role": config.ROLE_DALRRD}
