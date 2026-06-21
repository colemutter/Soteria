-- Tracked satellites / space objects.
--
-- One row per object, upserted from the frontend on `external_id`. Real
-- satellites use a deterministic external_id (`real-<norad>`) so re-adding the
-- same object updates the same row; theoretical (user-entered) objects use a
-- generated id. Identity/operator/physical fields that the live TLE feed can't
-- supply are left NULL and can be backfilled later.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.satellites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    external_id TEXT UNIQUE,
    norad_cat_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    operator TEXT,
    country TEXT,
    mission_class TEXT,
    operational_status TEXT NOT NULL DEFAULT 'active',

    -- Orbit source
    orbit_regime TEXT NOT NULL,
    tle_line1 TEXT,
    tle_line2 TEXT,
    tle_epoch TIMESTAMPTZ,
    reference_epoch TIMESTAMPTZ,

    -- Physical drag model
    mass_kg DOUBLE PRECISION,
    cross_section_area_m2 DOUBLE PRECISION,
    drag_coefficient DOUBLE PRECISION DEFAULT 2.2,
    ballistic_coefficient_kg_m2 DOUBLE PRECISION,

    -- Most recent computed state and the time it is valid for (so the position
    -- can be propagated / used in calculations later).
    position_time TIMESTAMPTZ,
    latitude_deg DOUBLE PRECISION,
    longitude_deg DOUBLE PRECISION,
    altitude_km DOUBLE PRECISION,
    speed_km_s DOUBLE PRECISION,

    -- Bookkeeping
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS satellites_norad_cat_id_idx
    ON public.satellites (norad_cat_id);
CREATE INDEX IF NOT EXISTS satellites_orbit_regime_idx
    ON public.satellites (orbit_regime);
CREATE INDEX IF NOT EXISTS satellites_position_time_idx
    ON public.satellites (position_time DESC);

-- The frontend writes with the public (anon) key, so expose the table and add
-- permissive RLS policies. NOTE: these allow any holder of the anon key to
-- read/insert/update rows — fine for a prototype; tighten before production.
GRANT SELECT, INSERT, UPDATE ON public.satellites TO anon, authenticated;

ALTER TABLE public.satellites ENABLE ROW LEVEL SECURITY;

CREATE POLICY "satellites_anon_select" ON public.satellites
    FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY "satellites_anon_insert" ON public.satellites
    FOR INSERT TO anon, authenticated WITH CHECK (true);

CREATE POLICY "satellites_anon_update" ON public.satellites
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
