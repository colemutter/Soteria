import { createClient, type SupabaseClient } from '@supabase/supabase-js'

/**
 * Shared Supabase client for frontend read-only data features.
 *
 * Configured via Vite env vars (put them in `src/frontend/.env`):
 *   VITE_SUPABASE_URL=...
 *   VITE_SUPABASE_ANON_KEY=...
 *
 * If either is missing the client is `null` and Supabase-backed frontend data
 * features become no-ops so the app still runs without credentials.
 */
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null

let warned = false
export function warnNoSupabaseOnce() {
  if (warned) return
  warned = true
  console.warn(
    '[supabase] VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY not set — ' +
      'Supabase-backed frontend data is disabled.',
  )
}
