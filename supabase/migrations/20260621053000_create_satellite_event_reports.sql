-- Validated event-window reports generated from Poller-triggered evidence.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.satellite_event_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dedupe_key TEXT NOT NULL UNIQUE,

    event_window_id UUID REFERENCES public.space_weather_event_windows (id)
        ON DELETE SET NULL,
    evidence_hash TEXT,
    status TEXT NOT NULL,
    session_id TEXT,

    report_json JSONB,
    failure_json JSONB,
    validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS satellite_event_reports_event_window_id_idx
    ON public.satellite_event_reports (event_window_id);
CREATE INDEX IF NOT EXISTS satellite_event_reports_evidence_hash_idx
    ON public.satellite_event_reports (evidence_hash);
CREATE INDEX IF NOT EXISTS satellite_event_reports_status_idx
    ON public.satellite_event_reports (status);

GRANT SELECT, INSERT, UPDATE ON public.satellite_event_reports TO anon, authenticated;

ALTER TABLE public.satellite_event_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "satellite_event_reports_anon_select"
    ON public.satellite_event_reports
    FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY "satellite_event_reports_anon_insert"
    ON public.satellite_event_reports
    FOR INSERT TO anon, authenticated WITH CHECK (true);

CREATE POLICY "satellite_event_reports_anon_update"
    ON public.satellite_event_reports
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
