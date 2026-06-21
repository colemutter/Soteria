-- Generated command runbooks from the AI/report pipeline.
--
-- Drafts received from generation and finalized uploaded runbooks share one
-- table so the backend can expose both workflow steps without inventing a
-- second storage shape.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.command_runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    report_id TEXT NOT NULL,
    satellite_id UUID REFERENCES public.satellites (id) ON DELETE SET NULL,
    satellite_external_id TEXT,

    title TEXT NOT NULL,
    summary TEXT,
    commands JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'generated',
    source TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS command_runbooks_report_id_idx
    ON public.command_runbooks (report_id);
CREATE INDEX IF NOT EXISTS command_runbooks_satellite_id_idx
    ON public.command_runbooks (satellite_id);
CREATE INDEX IF NOT EXISTS command_runbooks_satellite_external_id_idx
    ON public.command_runbooks (satellite_external_id);
CREATE INDEX IF NOT EXISTS command_runbooks_status_idx
    ON public.command_runbooks (status);

GRANT SELECT, INSERT, UPDATE ON public.command_runbooks TO anon, authenticated;

ALTER TABLE public.command_runbooks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "command_runbooks_anon_select" ON public.command_runbooks
    FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY "command_runbooks_anon_insert" ON public.command_runbooks
    FOR INSERT TO anon, authenticated WITH CHECK (true);

CREATE POLICY "command_runbooks_anon_update" ON public.command_runbooks
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
