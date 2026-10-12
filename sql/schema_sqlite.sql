-- AgriTrial MVP: LOCAL (on-phone) SQLite schema
-- Run automatically by database.init_sqlite_db(). Safe to run repeatedly.
--
-- Fixes vs the original schema:
--   * local_id (UUID) is the primary key; cloud_record_id (EP-T###) is stored separately
--   * nitrate/phosphate columns are named in mg/L (not ppm)
--   * every range from Section 6b is a real CHECK constraint (not just a comment)
--   * extra tables: users, sites, plots (protocols live in the cloud only)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Local copy of login details so a farmer can log in offline (salted hash only).
CREATE TABLE IF NOT EXISTS users (
    oid           TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL CHECK (role IN ('Small Farmer', 'DALRRD Regulatory Official', 'UWC Researcher')),
    full_name     TEXT,
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL
);

-- Site start date: used to calculate the trial week.
CREATE TABLE IF NOT EXISTS sites (
    site_id    TEXT PRIMARY KEY,
    start_date TEXT NOT NULL            -- YYYY-MM-DD
);

-- Plot = one site + one crop + one treatment group. Area is used for yield.
CREATE TABLE IF NOT EXISTS plots (
    plot_id            TEXT PRIMARY KEY,
    site_id            TEXT NOT NULL,
    crop_id            TEXT NOT NULL,
    treatment_group_id TEXT NOT NULL,
    area_m2            REAL NOT NULL CHECK (area_m2 > 0)
);

CREATE TABLE IF NOT EXISTS trial_measurements (
    local_id           TEXT PRIMARY KEY,     -- UUID made on the device
    cloud_record_id    TEXT,                 -- EP-T### assigned by the cloud on sync
    created_timestamp  TEXT NOT NULL,        -- 'YYYY-MM-DD HH:MM:SS'
    entry_date         TEXT NOT NULL,        -- 'YYYY-MM-DD'
    site_id            TEXT NOT NULL,
    environment_id     TEXT NOT NULL,
    crop_id            TEXT NOT NULL,
    treatment_group_id TEXT NOT NULL
        CHECK (treatment_group_id IN ('TGID-0','TGID-1','TGID-2','TGID-3','TGID-4','TGID-5')),
    plot_id            TEXT NOT NULL,
    trial_week         TEXT NOT NULL CHECK (trial_week GLOB 'TW-[0-9]*'),
    visit_type         TEXT NOT NULL CHECK (visit_type IN ('ROUTINE_MONITORING','HARVEST_VISIT')),
    observer_id        TEXT NOT NULL CHECK (observer_id GLOB 'OID-[0-9][0-9][0-9]'),

    -- Mandatory plant metrics
    plant_height_cm    REAL    NOT NULL CHECK (plant_height_cm > 0 AND plant_height_cm < 500),
    leaf_count         INTEGER NOT NULL CHECK (leaf_count >= 0 AND leaf_count < 500),

    -- Optional plant and harvest metrics
    fresh_weight_g     REAL CHECK (fresh_weight_g IS NULL OR (fresh_weight_g > 0 AND fresh_weight_g < 10000)),
    dry_weight_g       REAL CHECK (dry_weight_g   IS NULL OR (dry_weight_g   > 0 AND dry_weight_g   < 10000)),
    spad_index         REAL CHECK (spad_index     IS NULL OR (spad_index >= 0 AND spad_index <= 100)),
    root_length_cm     REAL CHECK (root_length_cm IS NULL OR (root_length_cm > 0 AND root_length_cm < 200)),

    -- Optional environmental readings
    ph_level           REAL CHECK (ph_level         IS NULL OR (ph_level >= 0 AND ph_level <= 14)),
    ec_level           REAL CHECK (ec_level         IS NULL OR (ec_level >= 0 AND ec_level <= 10)),
    dissolved_oxygen   REAL CHECK (dissolved_oxygen IS NULL OR (dissolved_oxygen >= 0 AND dissolved_oxygen <= 20)),
    temperature_c      REAL CHECK (temperature_c    IS NULL OR (temperature_c >= -10 AND temperature_c <= 60)),
    humidity_pct       REAL CHECK (humidity_pct     IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)),
    nitrate_mg_l       REAL CHECK (nitrate_mg_l     IS NULL OR (nitrate_mg_l > 0 AND nitrate_mg_l < 1000)),
    phosphate_mg_l     REAL CHECK (phosphate_mg_l   IS NULL OR (phosphate_mg_l > 0 AND phosphate_mg_l < 500)),
    notes              TEXT,

    -- Sync and audit flags (these exist on the phone only)
    sync_status        TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (sync_status IN ('PENDING','SYNCED','FLAGGED_FOR_REVIEW')),
    rejection_reason   TEXT,
    is_harvest_complete INTEGER NOT NULL DEFAULT 0 CHECK (is_harvest_complete IN (0,1)),
    last_edited_by     TEXT,
    last_edited_timestamp TEXT,

    -- dry weight can never exceed fresh weight (only checked when both are filled in)
    CHECK (dry_weight_g IS NULL OR fresh_weight_g IS NULL OR dry_weight_g <= fresh_weight_g)
);

CREATE INDEX IF NOT EXISTS idx_trial_sync ON trial_measurements (sync_status, created_timestamp);
CREATE INDEX IF NOT EXISTS idx_trial_plot ON trial_measurements (plot_id, visit_type);
