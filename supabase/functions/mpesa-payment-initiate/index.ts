import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const headers = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, idempotency-key",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json",
};
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers });
const env = (key: string) => Deno.env.get(key)?.trim() ?? "";
const normalizePhone = (value: unknown): string | null => {
  if (typeof value !== "string") return null;
  const digits = value.replace(/[\s()+-]/g, "");
  if (/^254[17]\d{8}$/.test(digits)) return digits;
  if (/^0[17]\d{8}$/.test(digits)) return "254" + digits.slice(1);
  if (/^[17]\d{8}$/.test(digits)) return "254" + digits;
  return null;
};
const timestampEAT = () => {
  const d = new Date(Date.now() + 3 * 60 * 60 * 1000);
  return d.toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
};
const base64 = (s: string) => btoa(unescape(encodeURIComponent(s)));

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers });
  if (req.method !== "POST") return reply({ error: "method_not_allowed" }, 405);

  // This function is deliberately sandbox-only. No production URL or switch is supported.
  const authorization = req.headers.get("Authorization");
  const url = env("SUPABASE_URL");
  const anon = env("SUPABASE_ANON_KEY") || env("SUPABASE_PUBLISHABLE_KEY");
  const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
  if (!authorization?.startsWith("Bearer ") || !url || !anon || !serviceKey)
    return reply({ error: "authentication_or_server_configuration_required" }, 401);

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser();
  if (userError || !userData.user) return reply({ error: "invalid_session" }, 401);

  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return reply({ error: "invalid_json" }, 400); }
  const flow = body.flow;
  const amount = body.amount;
  const phone = normalizePhone(body.phone);
  const idem = req.headers.get("Idempotency-Key") || body.idempotencyKey;
  if (flow !== "collection" && flow !== "payout") return reply({ error: "invalid_flow" }, 400);
  if (!phone) return reply({ error: "invalid_kenyan_phone_number" }, 400);
  if (typeof amount !== "number" || !Number.isSafeInteger(amount) || amount < (flow === "payout" ? 10 : 1) || amount > 250000)
    return reply({ error: "invalid_amount_kes" }, 400);
  if (typeof idem !== "string" || idem.length < 16 || idem.length > 100)
    return reply({ error: "idempotency_key_required" }, 400);

  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data: existing, error: existingError } = await admin.from("infigen_provider_payment_requests")
    .select("id,flow,amount_minor,phone_e164,status,provider_request_id,created_at")
    .eq("user_id", userData.user.id).eq("idempotency_key", idem).maybeSingle();
  if (existingError) return reply({ error: "payment_journal_unavailable" }, 503);
  if (existing) return reply({ status: "already_submitted_no_repeat_call", payment: existing }, 200);

  const { data: row, error: insertError } = await admin.from("infigen_provider_payment_requests").insert({
    user_id: userData.user.id, provider: "mpesa", flow, amount_minor: Number(amount) * 100,
    phone_e164: phone, idempotency_key: idem, status: "created",
  }).select("id,flow,amount_minor,phone_e164,status,created_at").single();
  if (insertError) {
    // A concurrent request with the same idempotency key must never trigger a second provider call.
    return reply({ error: "payment_request_not_created_or_duplicate_key", safeToRetryWithSameKey: false }, 409);
  }

  const callback = env("SUPABASE_URL").replace(/\/$/, "") + "/functions/v1/mpesa-payment-callback";
  const consumerKey = env("DARAJA_SANDBOX_CONSUMER_KEY") || env("DARAJA_CONSUMER_KEY");
  const consumerSecret = env("DARAJA_SANDBOX_CONSUMER_SECRET") || env("DARAJA_CONSUMER_SECRET");
  const tokenUrl = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials";
  if (!consumerKey || !consumerSecret) {
    await admin.from("infigen_provider_payment_requests").update({ status: "failed", provider_response: { error: "sandbox_credentials_missing" }, updated_at: new Date().toISOString() }).eq("id", row.id);
    return reply({ error: "mpesa_sandbox_credentials_missing", liveMoneyMovementEnabled: false }, 503);
  }

  try {
    const tokenResponse = await fetch(tokenUrl, {
      headers: { Authorization: "Basic " + btoa(consumerKey + ":" + consumerSecret) },
    });
    if (!tokenResponse.ok) throw new Error("sandbox_oauth_failed");
    const tokenJson = await tokenResponse.json();
    if (typeof tokenJson.access_token !== "string") throw new Error("sandbox_oauth_token_missing");
    let endpoint: string;
    let payload: Record<string, unknown>;

    if (flow === "collection") {
      const shortcode = env("DARAJA_SANDBOX_SHORTCODE") || env("DARAJA_SHORTCODE");
      const passkey = env("DARAJA_SANDBOX_PASSKEY") || env("DARAJA_PASSKEY");
      if (!shortcode || !passkey) throw new Error("mpesa_sandbox_stk_credentials_missing");
      const stamp = timestampEAT();
      endpoint = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest";
      payload = {
        BusinessShortCode: shortcode,
        Password: base64(shortcode + passkey + stamp),
        Timestamp: stamp,
        TransactionType: "CustomerPayBillOnline",
        Amount: Number(amount),
        PartyA: phone,
        PartyB: shortcode,
        PhoneNumber: phone,
        CallBackURL: callback,
        AccountReference: "INFIGEN-" + row.id.slice(0, 12),
        TransactionDesc: "InfiGen sandbox collection",
      };
    } else {
      const shortcode = env("DARAJA_SANDBOX_B2C_SHORTCODE") || env("MPESA_B2C_SHORTCODE");
      const initiator = env("DARAJA_SANDBOX_B2C_INITIATOR_NAME") || env("MPESA_B2C_INITIATOR_NAME");
      const credential = env("DARAJA_SANDBOX_B2C_SECURITY_CREDENTIAL") || env("MPESA_B2C_SECURITY_CREDENTIAL");
      if (!shortcode || !initiator || !credential) throw new Error("mpesa_sandbox_b2c_credentials_missing");
      endpoint = "https://sandbox.safaricom.co.ke/mpesa/b2c/v3/paymentrequest";
      payload = {
        OriginatorConversationID: row.id,
        InitiatorName: initiator,
        SecurityCredential: credential,
        CommandID: "BusinessPayment",
        Amount: Number(amount),
        PartyA: shortcode,
        PartyB: phone,
        Remarks: "InfiGen sandbox payout",
        QueueTimeOutURL: callback,
        ResultURL: callback,
        Occasion: row.id.slice(0, 20),
      };
    }

    const providerResponse = await fetch(endpoint, {
      method: "POST",
      headers: { Authorization: "Bearer " + tokenJson.access_token, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const providerJson = await providerResponse.json().catch(() => ({}));
    if (!providerResponse.ok) {
      await admin.from("infigen_provider_payment_requests").update({
        status: "failed", provider_response: { httpStatus: providerResponse.status, response: providerJson },
        updated_at: new Date().toISOString(),
      }).eq("id", row.id);
      return reply({ error: "mpesa_sandbox_request_rejected", paymentId: row.id, liveMoneyMovementEnabled: false }, 502);
    }
    const requestId = typeof providerJson.CheckoutRequestID === "string" ? providerJson.CheckoutRequestID : null;
    const conversationId = typeof providerJson.OriginatorConversationID === "string" ? providerJson.OriginatorConversationID :
      (typeof providerJson.ConversationID === "string" ? providerJson.ConversationID : row.id);
    await admin.from("infigen_provider_payment_requests").update({
      status: "submitted", provider_request_id: requestId, provider_conversation_id: conversationId,
      provider_response: providerJson, updated_at: new Date().toISOString(),
    }).eq("id", row.id);
    return reply({
      paymentId: row.id, flow, provider: "mpesa", status: "submitted",
      providerAcknowledgement: providerJson.ResponseDescription || providerJson.ResponseCode || "Request submitted to sandbox",
      note: "Sandbox acknowledgement is not final settlement. No account balance was credited or debited.",
      liveMoneyMovementEnabled: false,
    }, 202);
  } catch (error) {
    const safeMessage = error instanceof Error ? error.message : "sandbox_request_failed";
    await admin.from("infigen_provider_payment_requests").update({
      status: "needs_reconciliation", provider_response: { error: safeMessage }, updated_at: new Date().toISOString(),
    }).eq("id", row.id);
    return reply({ error: safeMessage, paymentId: row.id, status: "needs_reconciliation", doNotRetryWithNewKey: true, liveMoneyMovementEnabled: false }, 502);
  }
});
