-- AgriTrial MVP: CLOUD (Supabase / PostgreSQL) schema
-- Paste into Supabase -> SQL Editor -> New query -> Run.
--
-- Differences from the phone schema (on purpose):
--   * no sync_status / rejection_reason (those only exist on the phone)
--   * client_uuid = the phone's local_id. UNIQUE, so a retried sync updates the
--     same row instead of creating a duplicate
--   * record_id (EP-T101, EP-T102, ...) is assigned by the cloud, in arrival order
--   * proper Postgres types (date, timestamptz, numeric, boolean)

create sequence if not exists trial_record_seq start 101;

create table if not exists sites (
    site_id    text primary key,
    start_date date not null
);

create table if not exists plots (
    plot_id            text primary key,
    site_id            text not null references sites(site_id),
    crop_id            text not null,
    treatment_group_id text not null check (treatment_group_id in ('TGID-0','TGID-1','TGID-2','TGID-3','TGID-4','TGID-5')),
    area_m2            numeric not null check (area_m2 > 0)
);

-- One protocol description (Markdown) per treatment group.
create table if not exists protocols (
    tgid          text primary key check (tgid in ('TGID-0','TGID-1','TGID-2','TGID-3','TGID-4','TGID-5')),
    markdown_text text not null
);

-- Auth table: the ONLY place names and contact details are stored.
create table if not exists app_users (
    oid           text primary key check (oid ~ '^OID-[0-9]{3}$'),
    username      text not null unique,
    role          text not null check (role in ('Small Farmer','DALRRD Regulatory Official','UWC Researcher')),
    full_name     text,
    contact       text,
    salt          text not null,
    password_hash text not null
);

create table if not exists trial_measurements (
    client_uuid        text primary key,
    record_id          text not null unique default ('EP-T' || nextval('trial_record_seq')::text),
    created_timestamp  timestamptz not null,
    received_at        timestamptz not null default now(),
    entry_date         date not null,
    site_id            text not null,
    environment_id     text not null,
    crop_id            text not null,
    treatment_group_id text not null check (treatment_group_id in ('TGID-0','TGID-1','TGID-2','TGID-3','TGID-4','TGID-5')),
    plot_id            text not null,
    trial_week         text not null check (trial_week ~ '^TW-[1-9][0-9]*$'),
    visit_type         text not null check (visit_type in ('ROUTINE_MONITORING','HARVEST_VISIT')),
    observer_id        text not null check (observer_id ~ '^OID-[0-9]{3}$'),

    plant_height_cm    numeric not null check (plant_height_cm > 0 and plant_height_cm < 500),
    leaf_count         integer not null check (leaf_count >= 0 and leaf_count < 500),

    fresh_weight_g     numeric check (fresh_weight_g is null or (fresh_weight_g > 0 and fresh_weight_g < 10000)),
    dry_weight_g       numeric check (dry_weight_g   is null or (dry_weight_g   > 0 and dry_weight_g   < 10000)),
    spad_index         numeric check (spad_index     is null or (spad_index >= 0 and spad_index <= 100)),
    root_length_cm     numeric check (root_length_cm is null or (root_length_cm > 0 and root_length_cm < 200)),

    ph_level           numeric check (ph_level         is null or (ph_level >= 0 and ph_level <= 14)),
    ec_level           numeric check (ec_level         is null or (ec_level >= 0 and ec_level <= 10)),
    dissolved_oxygen   numeric check (dissolved_oxygen is null or (dissolved_oxygen >= 0 and dissolved_oxygen <= 20)),
    temperature_c      numeric check (temperature_c    is null or (temperature_c >= -10 and temperature_c <= 60)),
    humidity_pct       numeric check (humidity_pct     is null or (humidity_pct >= 0 and humidity_pct <= 100)),
    nitrate_mg_l       numeric check (nitrate_mg_l     is null or (nitrate_mg_l > 0 and nitrate_mg_l < 1000)),
    phosphate_mg_l     numeric check (phosphate_mg_l   is null or (phosphate_mg_l > 0 and phosphate_mg_l < 500)),
    notes              text,

    is_harvest_complete   boolean not null default false,
    last_edited_by        text,
    last_edited_timestamp timestamptz,

    check (dry_weight_g is null or fresh_weight_g is null or dry_weight_g <= fresh_weight_g)
);

create index if not exists idx_cloud_trials_lookup
    on trial_measurements (site_id, crop_id, treatment_group_id, trial_week);

-- Lock the tables down: only the service_role key (used by the FastAPI server)
-- can read/write. The phone never talks to Supabase directly.
alter table sites               enable row level security;
alter table plots               enable row level security;
alter table protocols           enable row level security;
alter table app_users           enable row level security;
alter table trial_measurements  enable row level security;
