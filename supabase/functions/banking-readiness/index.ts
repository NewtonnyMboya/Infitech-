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

  // Presence of credentials is not proof that a provider sandbox has passed certification.
  const mpesaCredentialsPresent = Boolean(
    Deno.env.get("DARAJA_CONSUMER_KEY") && Deno.env.get("DARAJA_CONSUMER_SECRET") &&
    Deno.env.get("DARAJA_SHORTCODE") && Deno.env.get("DARAJA_PASSKEY")
  );
  const airtelCredentialsPresent = Boolean(
    Deno.env.get("AIRTEL_CLIENT_ID") && Deno.env.get("AIRTEL_CLIENT_SECRET")
  );
  const mpesaApproved = Deno.env.get("MPESA_PRODUCTION_APPROVED") === "true";
  const airtelApproved = Deno.env.get("AIRTEL_PRODUCTION_APPROVED") === "true";

  return json({
    userId: data.user.id,
    environment: "pre_authorization",
    liveMoneyMovementEnabled: false,
    providers: {
      mpesa: {
        credentialsPresent: mpesaCredentialsPresent,
        sandboxAdapterImplemented: false,
        sandboxTested: false,
        productionApproved: mpesaApproved,
        status: "awaiting_credentials_and_sandbox_validation",
      },
      airtelMoney: {
        credentialsPresent: airtelCredentialsPresent,
        sandboxAdapterImplemented: false,
        sandboxTested: false,
        productionApproved: airtelApproved,
        status: "awaiting_credentials_and_sandbox_validation",
      },
    },
    nextSteps: [
      "Obtain M-PESA Daraja sandbox access and complete the provider's onboarding.",
      "Obtain Airtel Africa Money sandbox access and complete the provider's onboarding.",
      "Configure sandbox credentials only as Supabase Edge Function secrets; never in the APK or database.",
      "Implement provider-specific OAuth, request signing, timeout handling and token caching server-side.",
      "Implement authenticated, signature-verified callbacks with replay protection and idempotent ledger posting.",
      "Run successful, rejected, timeout, duplicate callback, reversal and reconciliation tests for each provider.",
      "Obtain written production approval and applicable legal/regulatory authorization before production activation.",
    ],
  });
});
