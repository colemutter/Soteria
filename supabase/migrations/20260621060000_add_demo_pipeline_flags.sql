-- Demo-mode routing flags for event windows and generated operator artifacts.
--
-- Demo event windows should generate demo reports and demo command runbooks; the
-- frontend alert feed can then switch between live and demo artifacts without a
-- parallel table shape.

ALTER TABLE public.space_weather_event_windows
    ADD COLUMN IF NOT EXISTS demo BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.satellite_event_reports
    ADD COLUMN IF NOT EXISTS demo BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.command_runbooks
    ADD COLUMN IF NOT EXISTS demo BOOLEAN NOT NULL DEFAULT false;

-- Treat the currently-seeded/generated operator artifacts as demo data so Demo
-- Mode can read them immediately after this migration is applied.
UPDATE public.command_runbooks
SET demo = true
WHERE demo IS DISTINCT FROM true;

UPDATE public.satellite_event_reports
SET demo = true
WHERE demo IS DISTINCT FROM true;

-- Keep their source windows aligned for polling/window-end lookups.
UPDATE public.space_weather_event_windows event_windows
SET demo = true
WHERE event_windows.id IN (
    SELECT event_window_id
    FROM public.command_runbooks
    WHERE event_window_id IS NOT NULL
    UNION
    SELECT event_window_id
    FROM public.satellite_event_reports
    WHERE event_window_id IS NOT NULL
);

CREATE INDEX IF NOT EXISTS space_weather_event_windows_demo_idx
    ON public.space_weather_event_windows (demo);

CREATE INDEX IF NOT EXISTS satellite_event_reports_demo_created_at_idx
    ON public.satellite_event_reports (demo, created_at DESC);

CREATE INDEX IF NOT EXISTS command_runbooks_demo_created_at_idx
    ON public.command_runbooks (demo, created_at DESC);

NOTIFY pgrst, 'reload schema';
