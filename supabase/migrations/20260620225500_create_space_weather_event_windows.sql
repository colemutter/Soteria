CREATE TABLE IF NOT EXISTS public.space_weather_event_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_key CHAR(64) NOT NULL,
    event_type TEXT NOT NULL,
    source_product TEXT NOT NULL,
    source_endpoint TEXT,
    window_start TIMESTAMPTZ NOT NULL,
    peak_time TIMESTAMPTZ,
    window_end TIMESTAMPTZ NOT NULL,
    peak_value DOUBLE PRECISION,
    peak_severity INTEGER,
    threshold_value DOUBLE PRECISION,
    units TEXT,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT space_weather_event_windows_event_key_key UNIQUE (event_key),
    CONSTRAINT space_weather_event_windows_event_key_hex
        CHECK (event_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT space_weather_event_windows_confidence_check
        CHECK (confidence IN ('forecast', 'observed', 'stale', 'uncertain')),
    CONSTRAINT space_weather_event_windows_status_check
        CHECK (status IN ('future', 'active', 'ended'))
);

CREATE INDEX IF NOT EXISTS space_weather_event_windows_type_time_idx
    ON public.space_weather_event_windows (event_type, window_start DESC);

CREATE INDEX IF NOT EXISTS space_weather_event_windows_status_idx
    ON public.space_weather_event_windows (status, confidence);

GRANT SELECT, INSERT, UPDATE ON public.space_weather_event_windows TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
