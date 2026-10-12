"""Cloud storage behind the API.

Two interchangeable back ends with the SAME methods:

* MockCloudStore  - a local SQLite file that behaves like the cloud. Used when
                    no Supabase keys are configured (development, tests, demo).
* SupabaseStore   - the real Supabase PostgreSQL database.

get_store() picks Supabase when SUPABASE_URL and SUPABASE_SERVICE_KEY are set
in the environment (.env), otherwise the mock. The rest of the system never
needs to know which one it is talking to.
"""
import os
import sqlite3

import config
from database import PAYLOAD_COLUMNS

# Column mapping: the phone's local_id is the cloud's client_uuid.
CLOUD_COLUMNS = [c for c in PAYLOAD_COLUMNS if c != "local_id"]


def _to_bool(value) -> bool:
    return bool(value) and value not in ("0", "false", "False")


def _normalise_trial(row: dict) -> dict:
    """Common shape returned by both stores."""
    row = dict(row)
    row["is_harvest_complete"] = _to_bool(row.get("is_harvest_complete"))
    return row


# =========================================================== local simulator ==
class MockCloudStore:
    """SQLite file that imitates the Supabase tables (same names and behaviour)."""

    name = "local-simulator"

    def __init__(self, path: str):
        self.path = path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        cols = ", ".join(CLOUD_COLUMNS)  # typeless columns are fine in SQLite
        with self._conn() as c:
            c.executescript(f"""
                CREATE TABLE IF NOT EXISTS sites (site_id TEXT PRIMARY KEY, start_date TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS plots (plot_id TEXT PRIMARY KEY, site_id TEXT, crop_id TEXT,
                    treatment_group_id TEXT, area_m2 REAL);
                CREATE TABLE IF NOT EXISTS protocols (tgid TEXT PRIMARY KEY, markdown_text TEXT);
                CREATE TABLE IF NOT EXISTS app_users (oid TEXT PRIMARY KEY, username TEXT UNIQUE,
                    role TEXT, full_name TEXT, contact TEXT, salt TEXT, password_hash TEXT);
                CREATE TABLE IF NOT EXISTS trial_measurements (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE,
                    client_uuid TEXT UNIQUE NOT NULL,
                    {cols});
            """)

    def reset(self):
        with self._conn() as c:
            for table in ("trial_measurements", "sites", "plots", "protocols", "app_users"):
                c.execute(f"DELETE FROM {table}")
            c.execute("DELETE FROM sqlite_sequence")  # EP-T101 again on the next record

    def ping(self) -> bool:
        return True

    # ---- setup data ("Server Wins": the first one to arrive sets the baseline)
    def get_site(self, site_id):
        with self._conn() as c:
            r = c.execute("SELECT * FROM sites WHERE site_id = ?", (site_id,)).fetchone()
        return dict(r) if r else None

    def create_site_if_absent(self, site_id, start_date):
        if not self.get_site(site_id):
            with self._conn() as c:
                c.execute("INSERT INTO sites VALUES (?, ?)", (site_id, start_date))
        return self.get_site(site_id)

    def list_sites(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM sites")]

    def get_plot(self, plot_id):
        with self._conn() as c:
            r = c.execute("SELECT * FROM plots WHERE plot_id = ?", (plot_id,)).fetchone()
        return dict(r) if r else None

    def create_plot_if_absent(self, plot):
        if not self.get_plot(plot["plot_id"]):
            with self._conn() as c:
                c.execute("INSERT INTO plots VALUES (?, ?, ?, ?, ?)",
                          (plot["plot_id"], plot["site_id"], plot["crop_id"],
                           plot["treatment_group_id"], plot["area_m2"]))
        return self.get_plot(plot["plot_id"])

    def list_plots(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM plots")]

    def get_protocol(self, tgid):
        with self._conn() as c:
            r = c.execute("SELECT markdown_text FROM protocols WHERE tgid = ?", (tgid,)).fetchone()
        return r["markdown_text"] if r else None

    def set_protocol(self, tgid, text):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO protocols VALUES (?, ?)", (tgid, text))

    # ---- users
    def get_user(self, username):
        with self._conn() as c:
            r = c.execute("SELECT * FROM app_users WHERE username = ?", (username,)).fetchone()
        return dict(r) if r else None

    def next_oid(self):
        """Farmers get OID-101, OID-102, ... (900+ is reserved for stakeholders)."""
        with self._conn() as c:
            rows = [r["oid"] for r in c.execute("SELECT oid FROM app_users")]
        numbers = [int(o[4:]) for o in rows if 100 <= int(o[4:]) < 900]
        return f"OID-{(max(numbers) + 1) if numbers else 101}"

    def create_user(self, username, role, full_name, contact, salt, password_hash, oid=None):
        oid = oid or self.next_oid()
        with self._conn() as c:
            c.execute("INSERT INTO app_users VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (oid, username, role, full_name, contact, salt, password_hash))
        return oid

    # ---- trial records
    def upsert_trial(self, rec) -> str:
        """Insert or update by client_uuid. Returns the cloud Record ID (EP-T###)."""
        uuid_ = rec["local_id"]
        row = {c: rec.get(c) for c in CLOUD_COLUMNS}
        row["is_harvest_complete"] = 1 if rec.get("is_harvest_complete") else 0
        with self._conn() as c:
            existing = c.execute("SELECT record_id FROM trial_measurements WHERE client_uuid = ?",
                                 (uuid_,)).fetchone()
            if existing:  # an edit: keep the permanent record_id
                sets = ", ".join(f"{k} = ?" for k in row)
                c.execute(f"UPDATE trial_measurements SET {sets} WHERE client_uuid = ?",
                          [*row.values(), uuid_])
                return existing["record_id"]
            names = ", ".join(["client_uuid", *row])
            marks = ", ".join("?" for _ in range(len(row) + 1))
            cur = c.execute(f"INSERT INTO trial_measurements ({names}) VALUES ({marks})",
                            [uuid_, *row.values()])
            record_id = f"EP-T{100 + cur.lastrowid}"
            c.execute("UPDATE trial_measurements SET record_id = ? WHERE seq = ?",
                      (record_id, cur.lastrowid))
            return record_id

    def list_trials(self, **filters):
        sql, args = "SELECT * FROM trial_measurements WHERE 1=1", []
        for key, value in filters.items():
            if value is not None:
                sql += f" AND {key} = ?"
                args.append(value)
        sql += " ORDER BY seq"
        with self._conn() as c:
            return [_normalise_trial(r) for r in c.execute(sql, args)]


# ================================================================== Supabase ==
class SupabaseStore:
    """Real Supabase back end. Same methods as MockCloudStore."""

    name = "supabase"

    def __init__(self, url: str, key: str):
        from supabase import create_client  # imported here so the mock needs no keys
        self.sb = create_client(url, key)

    def _rows(self, table, **eq):
        query = self.sb.table(table).select("*")
        for k, v in eq.items():
            if v is not None:
                query = query.eq(k, v)
        return query.execute().data

    def ping(self) -> bool:
        """False when the project is paused (free-tier 7-day inactivity) or unreachable."""
        try:
            self.sb.table("sites").select("site_id").limit(1).execute()
            return True
        except Exception:
            return False

    def reset(self):
        for table, col in (("trial_measurements", "client_uuid"), ("plots", "plot_id"),
                           ("sites", "site_id"), ("protocols", "tgid"), ("app_users", "oid")):
            self.sb.table(table).delete().neq(col, "").execute()

    def get_site(self, site_id):
        rows = self._rows("sites", site_id=site_id)
        return rows[0] if rows else None

    def create_site_if_absent(self, site_id, start_date):
        if not self.get_site(site_id):
            self.sb.table("sites").insert({"site_id": site_id, "start_date": start_date}).execute()
        return self.get_site(site_id)

    def list_sites(self):
        return self._rows("sites")

    def get_plot(self, plot_id):
        rows = self._rows("plots", plot_id=plot_id)
        return rows[0] if rows else None

    def create_plot_if_absent(self, plot):
        if not self.get_plot(plot["plot_id"]):
            self.sb.table("plots").insert(plot).execute()
        return self.get_plot(plot["plot_id"])

    def list_plots(self):
        return self._rows("plots")

    def get_protocol(self, tgid):
        rows = self._rows("protocols", tgid=tgid)
        return rows[0]["markdown_text"] if rows else None

    def set_protocol(self, tgid, text):
        self.sb.table("protocols").upsert({"tgid": tgid, "markdown_text": text}).execute()

    def get_user(self, username):
        rows = self._rows("app_users", username=username)
        return rows[0] if rows else None

    def next_oid(self):
        rows = [r["oid"] for r in self._rows("app_users")]
        numbers = [int(o[4:]) for o in rows if 100 <= int(o[4:]) < 900]
        return f"OID-{(max(numbers) + 1) if numbers else 101}"

    def create_user(self, username, role, full_name, contact, salt, password_hash, oid=None):
        oid = oid or self.next_oid()
        self.sb.table("app_users").insert({
            "oid": oid, "username": username, "role": role, "full_name": full_name,
            "contact": contact, "salt": salt, "password_hash": password_hash}).execute()
        return oid

    def upsert_trial(self, rec) -> str:
        row = {c: rec.get(c) for c in CLOUD_COLUMNS}
        row["client_uuid"] = rec["local_id"]
        row["is_harvest_complete"] = bool(rec.get("is_harvest_complete"))
        self.sb.table("trial_measurements").upsert(row, on_conflict="client_uuid").execute()
        saved = self._rows("trial_measurements", client_uuid=rec["local_id"])
        return saved[0]["record_id"]

    def list_trials(self, **filters):
        return [_normalise_trial(r) for r in self._rows("trial_measurements", **filters)]


# ============================================================== factory ======
_store = None


def get_store():
    """Return the active store (created on first use)."""
    global _store
    if _store is None:
        url = os.getenv("SUPABASE_URL") or config.SUPABASE_URL
        key = os.getenv("SUPABASE_SERVICE_KEY") or config.SUPABASE_SERVICE_KEY
        _store = SupabaseStore(url, key) if (url and key) else MockCloudStore(config.CLOUD_MOCK_DB)
    return _store


def set_store(store) -> None:
    """Swap the store (used by tests)."""
    global _store
    _store = store
