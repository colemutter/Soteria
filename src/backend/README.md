## Render validation scripts

Seed two fake space-weather event windows in Supabase: one severe solar-wind
coupling event and one severe geomagnetic storm event. Event keys are random by
default so each run creates fresh rows. Pass `--stable-keys` to update the same
rows by `event_key`. When `SUPABASE_DATABASE_URL` is configured, the script
writes with `supabase db query`; otherwise it falls back to the Supabase Data
API.

```bash
uv run python scripts/seed_fake_space_weather_events.py
```

Preview the rows without writing:

```bash
uv run python scripts/seed_fake_space_weather_events.py --dry-run
```

Smoke-test deployed Render routes:

```bash
uv run python scripts/render_endpoint_smoke_test.py
```

Run a guarded live pipeline validation against Render. This uses the linked
Supabase CLI project to seed marked validation rows, then waits for the deployed
Render poller/backend pipeline to persist `satellite_event_reports` and
`command_runbooks` rows:

```bash
RUN_RENDER_PIPELINE_TESTS=true uv run python scripts/render_poller_pipeline_validation.py
```

To isolate the backend report pipeline from the deployed worker loop, post the
seeded batch directly to Render:

```bash
RUN_RENDER_PIPELINE_TESTS=true uv run python scripts/render_poller_pipeline_validation.py --dispatch-mode direct-report-post
```

Use `--base-url https://...` or `SOTERIA_RENDER_BACKEND_URL` to test a Render
preview service. Use `SOTERIA_DOTENV_OVERRIDE=true` when local shell credentials
should be replaced by `src/backend/.env`.

If every endpoint returns `404`, the URL is not serving the FastAPI backend.
Update the Render service URL in `render.yaml` or pass the real URL with
`--base-url`.
