import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, idempotency-key",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json",
};
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: corsHeaders });
}
Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  const authorization = req.headers.get("Authorization");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  if (!authorization?.startsWith("Bearer ") || !supabaseUrl || !anonKey) return json({ error: "authentication_required" }, 401);
  const supabase = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return json({ error: "invalid_session" }, 401);
  let body: { provider?: unknown; amountKes?: unknown; mode?: unknown };
  try { body = await req.json(); } catch { return json({ error: "invalid_json" }, 400); }
  if (!["mpesa", "airtel_money"].includes(String(body.provider))) return json({ error: "unsupported_provider" }, 400);
  if (!Number.isSafeInteger(body.amountKes) || Number(body.amountKes) < 1 || Number(body.amountKes) > 100000) {
    return json({ error: "amount_must_be_whole_KES_between_1_and_100000" }, 400);
  }
  // Fail closed: this endpoint deliberately does not initiate or claim a real payment.
  // Provider OAuth, request signing, callbacks, reconciliation and approval are not yet deployed.
  if (body.mode === "production") return json({
    error: "live_payments_disabled",
    message: "Live payments are disabled pending provider approval, secure callback verification, reconciliation and production authorization.",
  }, 403);
  return json({
    error: "provider_sandbox_not_integrated",
    message: "No payment was initiated. Complete the provider sandbox adapter and callback tests before enabling sandbox checkout.",
    provider: body.provider, mode: "sandbox", liveMoneyMovementEnabled: false,
  }, 503);
});
