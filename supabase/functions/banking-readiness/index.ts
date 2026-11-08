import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Content-Type": "application/json",
};
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: corsHeaders });
}
Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "GET") return json({ error: "method_not_allowed" }, 405);
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
  const mpesaApproved = Deno.env.get("MPESA_PRODUCTION_APPROVED") === "true";
  const airtelApproved = Deno.env.get("AIRTEL_PRODUCTION_APPROVED") === "true";
  const mpesaConfigured = Boolean(Deno.env.get("DARAJA_CONSUMER_KEY") && Deno.env.get("DARAJA_CONSUMER_SECRET") && Deno.env.get("DARAJA_SHORTCODE") && Deno.env.get("DARAJA_PASSKEY"));
  const airtelConfigured = Boolean(Deno.env.get("AIRTEL_CLIENT_ID") && Deno.env.get("AIRTEL_CLIENT_SECRET"));
  return json({
    userId: data.user.id,
    liveMoneyMovementEnabled: false,
    providers: {
      mpesa: { sandboxReady: mpesaConfigured, productionApproved: mpesaApproved, status: mpesaApproved && mpesaConfigured ? "requires_end_to_end_validation" : "not_ready" },
      airtelMoney: { sandboxReady: airtelConfigured, productionApproved: airtelApproved, status: airtelApproved && airtelConfigured ? "requires_end_to_end_validation" : "not_ready" },
    },
    requirements: [
      "Complete provider onboarding and written production approval",
      "Configure credentials as Supabase Edge Function secrets",
      "Implement and verify authentic provider callbacks",
      "Run reconciliation, idempotency, reversal, fraud and security tests",
      "Obtain applicable financial-services authorization before live use",
    ],
  });
});
