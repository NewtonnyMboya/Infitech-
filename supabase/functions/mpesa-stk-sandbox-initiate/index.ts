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
function validPhone(value: unknown): value is string {
  return typeof value === "string" && /^254[17][0-9]{8}$/.test(value);
}
function timestampNairobi(): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Nairobi", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date());
  const p = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${p.year}${p.month}${p.day}${p.hour}${p.minute}${p.second}`;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  const authorization = req.headers.get("Authorization");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!authorization?.startsWith("Bearer ") || !supabaseUrl || !anonKey || !serviceRoleKey) {
    return json({ error: "authentication_required" }, 401);
  }

  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: authData, error: authError } = await userClient.auth.getUser();
  if (authError || !authData.user) return json({ error: "invalid_session" }, 401);

  const idempotencyKey = req.headers.get("Idempotency-Key")?.trim() ?? "";
  if (idempotencyKey.length < 8 || idempotencyKey.length > 120 ||
      !/^[A-Za-z0-9._:-]+$/.test(idempotencyKey)) {
    return json({ error: "valid_idempotency_key_required" }, 400);
  }

  let body: { accountId?: unknown; amountKes?: unknown; phone?: unknown };
  try { body = await req.json(); } catch { return json({ error: "invalid_json" }, 400); }
  if (typeof body.accountId !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(body.accountId)) {
    return json({ error: "valid_account_id_required" }, 400);
  }
  if (!Number.isSafeInteger(body.amountKes) || Number(body.amountKes) < 1 || Number(body.amountKes) > 100000) {
    return json({ error: "amount_must_be_whole_KES_between_1_and_100000" }, 400);
  }
  if (!validPhone(body.phone)) {
    return json({ error: "phone_must_be_Kenyan_in_254_format" }, 400);
  }

  // This endpoint is intentionally sandbox-only. Production credentials/endpoints are never selected here.
  const callbackUrl = Deno.env.get("MPESA_STK_CALLBACK_URL")?.trim();
  const consumerKey = Deno.env.get("DARAJA_CONSUMER_KEY")?.trim();
  const consumerSecret = Deno.env.get("DARAJA_CONSUMER_SECRET")?.trim();
  const shortcode = Deno.env.get("DARAJA_SHORTCODE")?.trim();
  const passkey = Deno.env.get("DARAJA_PASSKEY")?.trim();
  if (!callbackUrl || !consumerKey || !consumerSecret || !shortcode || !passkey) {
    return json({ error: "mpesa_sandbox_not_configured", liveMoneyMovementEnabled: false }, 503);
  }
  try {
    const callback = new URL(callbackUrl);
    if (callback.protocol !== "https:" || callback.hostname === "localhost" ||
        callback.hostname === "127.0.0.1") throw new Error("invalid_callback_url");
  } catch {
    return json({ error: "public_https_callback_url_required" }, 503);
  }

  const admin = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  // Idempotent retries never send a second STK prompt. Ambiguous attempts must be reconciled.
  const { data: prior, error: priorError } = await admin.from("infigen_payment_intents")
    .select("id,status,provider_checkout_request_id,amount_minor,created_at")
    .eq("user_id", authData.user.id).eq("idempotency_key", idempotencyKey).maybeSingle();
  if (priorError) return json({ error: "temporarily_unavailable" }, 503);
  if (prior) {
    return json({
      intentId: prior.id, status: prior.status,
      checkoutRequestId: prior.provider_checkout_request_id,
      reused: true, message: "No new prompt was sent for this idempotency key.",
      liveMoneyMovementEnabled: false,
    }, 200);
  }

  const { data: account, error: accountError } = await admin.from("infigen_accounts")
    .select("id,owner_id,account_type,currency,status")
    .eq("id", body.accountId).eq("owner_id", authData.user.id).maybeSingle();
  if (accountError) return json({ error: "temporarily_unavailable" }, 503);
  if (!account || account.currency !== "KES" || !["demo", "live"].includes(account.account_type)) {
    return json({ error: "account_not_found_or_unsupported" }, 404);
  }

  const amountMinor = Number(body.amountKes) * 100;
  const reference = "IG" + crypto.randomUUID().replaceAll("-", "").slice(0, 10);
  const { data: intent, error: intentError } = await admin.from("infigen_payment_intents").insert({
    user_id: authData.user.id,
    account_id: account.id,
    provider: "mpesa",
    flow: "collection",
    environment: "sandbox",
    amount_minor: amountMinor,
    currency: "KES",
    phone_e164: body.phone,
    account_reference: reference,
    transaction_description: "InfiGen sandbox collection",
    idempotency_key: idempotencyKey,
    status: "pending",
  }).select("id,created_at").single();
  if (intentError || !intent) return json({ error: "could_not_create_payment_intent" }, 503);

  const markUnknown = async () => {
    await admin.from("infigen_payment_intents").update({
      status: "unknown", updated_at: new Date().toISOString(),
    }).eq("id", intent.id);
  };

  try {
    const oauth = await fetch("https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials", {
      method: "GET",
      headers: { Authorization: "Basic " + btoa(consumerKey + ":" + consumerSecret) },
      signal: AbortSignal.timeout(12000),
    });
    if (!oauth.ok) {
      await markUnknown();
      return json({ intentId: intent.id, status: "unknown", error: "provider_authentication_failed_no_success_claimed" }, 502);
    }
    const tokenBody = await oauth.json();
    if (typeof tokenBody.access_token !== "string" || !tokenBody.access_token) {
      await markUnknown();
      return json({ intentId: intent.id, status: "unknown", error: "provider_authentication_failed_no_success_claimed" }, 502);
    }

    const timestamp = timestampNairobi();
    const password = btoa(shortcode + passkey + timestamp);
    const requestBody = {
      BusinessShortCode: shortcode,
      Password: password,
      Timestamp: timestamp,
      TransactionType: "CustomerPayBillOnline",
      Amount: Number(body.amountKes),
      PartyA: body.phone,
      PartyB: shortcode,
      PhoneNumber: body.phone,
      CallBackURL: callbackUrl,
      AccountReference: reference,
      TransactionDesc: "InfiGen sandbox collection",
    };
    const response = await fetch("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", {
      method: "POST",
      headers: { Authorization: "Bearer " + tokenBody.access_token, "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: AbortSignal.timeout(15000),
    });
    const providerBody = await response.json().catch(() => ({}));
    if (!response.ok || typeof providerBody.CheckoutRequestID !== "string") {
      await markUnknown();
      return json({
        intentId: intent.id, status: "unknown",
        error: "provider_did_not_confirm_request_acceptance",
        liveMoneyMovementEnabled: false,
      }, 502);
    }

    const { error: updateError } = await admin.from("infigen_payment_intents").update({
      status: "provider_accepted",
      provider_checkout_request_id: providerBody.CheckoutRequestID,
      provider_merchant_request_id: typeof providerBody.MerchantRequestID === "string" ? providerBody.MerchantRequestID : null,
      updated_at: new Date().toISOString(),
    }).eq("id", intent.id);
    if (updateError) {
      // The provider may have accepted the request; never retry initiation automatically.
      await markUnknown();
      return json({ intentId: intent.id, status: "unknown", error: "accepted_request_requires_reconciliation" }, 202);
    }

    return json({
      intentId: intent.id,
      status: "provider_accepted",
      checkoutRequestId: providerBody.CheckoutRequestID,
      customerMessage: "Sandbox STK prompt requested. Payment is not confirmed until provider verification.",
      liveMoneyMovementEnabled: false,
    }, 202);
  } catch {
    await markUnknown();
    return json({
      intentId: intent.id,
      status: "unknown",
      error: "provider_timeout_or_network_error_reconcile_before_retry",
      liveMoneyMovementEnabled: false,
    }, 202);
  }
});
