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
function allConfigured(names: string[]): boolean {
  return names.every(configured);
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

  // Readiness is informational only. Configured secrets never imply provider approval,
  // correct credentials, successful certification, or permission to move real money.
  const mpesaCollectionRequired = [
    "DARAJA_CONSUMER_KEY",
    "DARAJA_CONSUMER_SECRET",
    "DARAJA_SHORTCODE",
    "DARAJA_PASSKEY",
    "MPESA_STK_CALLBACK_URL",
  ];
  const mpesaPayoutRequired = [
    "DARAJA_CONSUMER_KEY",
    "DARAJA_CONSUMER_SECRET",
    "MPESA_B2C_SHORTCODE",
    "MPESA_B2C_INITIATOR_NAME",
    "MPESA_B2C_SECURITY_CREDENTIAL",
    "MPESA_B2C_RESULT_URL",
    "MPESA_B2C_TIMEOUT_URL",
  ];
  const mpesaCollectionCredentialsPresent = allConfigured(mpesaCollectionRequired);
  const mpesaPayoutCredentialsPresent = allConfigured(mpesaPayoutRequired);
  const mpesaCollectionApproved = Deno.env.get("MPESA_STK_PRODUCTION_APPROVED") === "true";
  const mpesaPayoutApproved = Deno.env.get("MPESA_B2C_PRODUCTION_APPROVED") === "true";

  const airtelCredentialsPresent = configured("AIRTEL_CLIENT_ID") &&
    configured("AIRTEL_CLIENT_SECRET");
  const airtelApproved = Deno.env.get("AIRTEL_PRODUCTION_APPROVED") === "true";

  const capability = (credentialsPresent: boolean, approved: boolean) => ({
    credentialsPresent,
    adapterImplemented: false,
    sandboxTested: false,
    productionApproved: approved,
    liveMoneyMovementEnabled: false,
    status: "blocked_pending_adapter_tests_and_approval",
  });

  return json({
    userId: data.user.id,
    environment: "pre_authorization",
    liveMoneyMovementEnabled: false,
    productionAuthorizationStatus: "pending",
    note: "Configuration reporting only. Secret presence is not verified against the provider and never enables a payment.",
    providers: {
      mpesa: {
        collection: capability(mpesaCollectionCredentialsPresent, mpesaCollectionApproved),
        payout: capability(mpesaPayoutCredentialsPresent, mpesaPayoutApproved),
      },
      airtelMoney: {
        credentialsPresent: airtelCredentialsPresent,
        collection: capability(airtelCredentialsPresent, airtelApproved),
        payout: capability(airtelCredentialsPresent, airtelApproved),
      },
    },
    requiredGates: [
      "M-PESA collection and payout are separate products and must be enabled and tested separately.",
      "Obtain Safaricom Daraja sandbox credentials and verify the current API contract for the exact product.",
      "Implement server-side OAuth, request construction, callback validation, replay protection and idempotency.",
      "For B2C payout, obtain the correct live disbursement shortcode/account and authorized API initiator as required by Safaricom.",
      "Reconcile uncertain outcomes with Safaricom's transaction-status API; asynchronous acknowledgements are not final success.",
      "Post ledger entries atomically and exactly once only after independently verified provider success.",
      "Pass success, rejection, cancellation, timeout, duplicate initiation/callback, invalid callback, reconciliation and reversal tests.",
      "Obtain written production approval for the exact M-PESA product and complete security, legal/compliance and operational reviews.",
      "Only a separately reviewed release may change the production gate; setting an environment variable alone must never enable live money movement.",
    ],
  });
});
