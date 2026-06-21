-- Catalog-backed generated command runbook persistence metadata.
--
-- Existing uploaded rows remain compatible: catalog columns and dedupe_key are
-- nullable, while generated rows are validated by the backend before upsert.

ALTER TABLE public.command_runbooks
    ADD COLUMN IF NOT EXISTS event_window_id UUID
        REFERENCES public.space_weather_event_windows (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS catalog_version TEXT,
    ADD COLUMN IF NOT EXISTS policy_version TEXT,
    ADD COLUMN IF NOT EXISTS evidence_hash TEXT,
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'command_runbooks_dedupe_key_key'
    ) THEN
        ALTER TABLE public.command_runbooks
            ADD CONSTRAINT command_runbooks_dedupe_key_key UNIQUE (dedupe_key);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS command_runbooks_event_window_id_idx
    ON public.command_runbooks (event_window_id);
CREATE INDEX IF NOT EXISTS command_runbooks_catalog_version_idx
    ON public.command_runbooks (catalog_version);
CREATE INDEX IF NOT EXISTS command_runbooks_policy_version_idx
    ON public.command_runbooks (policy_version);
CREATE INDEX IF NOT EXISTS command_runbooks_evidence_hash_idx
    ON public.command_runbooks (evidence_hash);

NOTIFY pgrst, 'reload schema';
