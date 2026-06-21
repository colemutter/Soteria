-- Demo space-weather data: a synthetic "storm" scenario that starts at normal
-- (quiet) conditions and escalates over a 2-day window to an extreme G5-class
-- geomagnetic storm — severe enough that satellite operators would take
-- protective action. Same format as public.swpc_forecast_records.
--
-- The frontend re-anchors the earliest timestamp to "now" on read, so the fixed
-- base date below is just a reference; the profile always spans now → +2 days.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.swpc_forecast_records_demo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    record_hash CHAR(64) NOT NULL,
    product_type TEXT NOT NULL,
    issued_at TIMESTAMPTZ,
    valid_start TIMESTAMPTZ,
    valid_end TIMESTAMPTZ,
    observed BOOLEAN,
    severity INTEGER,
    value DOUBLE PRECISION,
    units TEXT,
    record JSONB NOT NULL,
    raw_payload_id UUID,
    source TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT swpc_forecast_records_demo_record_hash_key UNIQUE (record_hash),
    CONSTRAINT swpc_forecast_records_demo_record_hash_hex
        CHECK (record_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS swpc_forecast_records_demo_product_valid_idx
    ON public.swpc_forecast_records_demo (product_type, valid_start);

GRANT SELECT, INSERT, UPDATE ON public.swpc_forecast_records_demo
    TO anon, authenticated;

-- Hourly profile over 48 h. `ramp` is 0 for the first day, then climbs 0→1 over
-- the second day, so each driver stays normal then escalates sharply:
--   Kp  : 2  (quiet)        → 9   (G5 extreme)
--   Bz  : +3 (northward)    → -28 nT (strongly southward = geoeffective)
--   Bt  : 5  → 35 nT (strong interplanetary field, CME-like)
INSERT INTO public.swpc_forecast_records_demo
    (endpoint, record_hash, product_type, valid_start, observed, value, units,
     record, source, fetched_at)
SELECT
    'demo',
    -- 64-char lowercase hex (two md5s) to satisfy the record_hash format,
    -- using only core functions (no pgcrypto schema dependency).
    md5('demo:' || p.product_type || ':' || h::text)
        || md5('demo2:' || p.product_type || ':' || h::text),
    p.product_type,
    TIMESTAMPTZ '2026-06-21 00:00:00+00' + (h::text || ' hours')::interval,
    false,
    p.value,
    p.units,
    '{}'::jsonb,
    'demo',
    NOW()
FROM generate_series(0, 48) AS h
CROSS JOIN LATERAL (
    SELECT GREATEST(0, h - 24)::numeric / 24.0 AS ramp
) r
CROSS JOIN LATERAL (
    VALUES
        ('kp_forecast',          LEAST(9.0, 2.0 + 7.0 * r.ramp),  'Kp'),
        ('solar_wind_mag_bz_gsm', 3.0 - 31.0 * r.ramp,            'nT'),
        ('solar_wind_mag_bt',     5.0 + 30.0 * r.ramp,            'nT')
) AS p(product_type, value, units);
