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
function configured(name: string): boolean {
  return Boolean(Deno.env.get(name)?.trim());
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

  // Readiness is informational only. Credentials never imply approval or a tested adapter.
  const mpesaCredentialsPresent = configured("DARAJA_CONSUMER_KEY") &&
    configured("DARAJA_CONSUMER_SECRET") && configured("DARAJA_SHORTCODE") &&
    configured("DARAJA_PASSKEY");
  const airtelCredentialsPresent = configured("AIRTEL_CLIENT_ID") &&
    configured("AIRTEL_CLIENT_SECRET");
  const mpesaApproved = Deno.env.get("MPESA_PRODUCTION_APPROVED") === "true";
  const airtelApproved = Deno.env.get("AIRTEL_PRODUCTION_APPROVED") === "true";

  const provider = (credentialsPresent: boolean, approved: boolean) => ({
    credentialsPresent,
    collection: {
      adapterImplemented: false,
      sandboxTested: false,
      productionApproved: approved,
      status: "blocked_pending_adapter_tests_and_approval",
    },
    payout: {
      adapterImplemented: false,
      sandboxTested: false,
      productionApproved: approved,
      status: "blocked_pending_adapter_tests_and_approval",
    },
  });

  return json({
    userId: data.user.id,
    environment: "pre_authorization",
    liveMoneyMovementEnabled: false,
    productionAuthorizationStatus: "pending",
    note: "This endpoint reports configuration only. It does not initiate payments or certify provider access.",
    providers: {
      mpesa: provider(mpesaCredentialsPresent, mpesaApproved),
      airtelMoney: provider(airtelCredentialsPresent, airtelApproved),
    },
    requiredGates: [
      "Obtain provider sandbox access and verify the current country/product API contract.",
      "Implement separate server-side collection and payout adapters for each provider.",
      "Verify provider callbacks, protect against replay, and make event processing idempotent.",
      "Reconcile uncertain results with provider status APIs; timeouts must remain pending/unknown.",
      "Post ledger entries atomically only after independently verified provider success.",
      "Pass success, rejection, cancellation, timeout, duplicate initiation/callback, invalid callback, reconciliation and reversal tests.",
      "Obtain written production approval for each exact provider/product and complete legal/compliance and operational reviews.",
    ],
  });
});
