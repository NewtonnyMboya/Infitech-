import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const headers = { "Content-Type": "application/json" };
function reply(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers });
}
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function safeString(value: unknown, max = 160): string | null {
  return typeof value === "string" ? value.slice(0, max) : null;
}
function metadataItems(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const items = (value as { Item?: unknown }).Item;
  if (!Array.isArray(items)) return {};
  const out: Record<string, unknown> = {};
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const row = item as { Name?: unknown; Value?: unknown };
    if (typeof row.Name === "string") out[row.Name] = row.Value;
  }
  return out;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return reply(405, { error: "method_not_allowed" });

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) {
    // Avoid disclosing configuration details to the public callback caller.
    return reply(503, { error: "temporarily_unavailable" });
  }

  let raw: string;
  try { raw = await req.text(); } catch { return reply(400, { error: "invalid_body" }); }
  if (!raw || raw.length > 64_000) return reply(400, { error: "invalid_body" });

  let payload: Record<string, unknown>;
  try { payload = JSON.parse(raw) as Record<string, unknown>; }
  catch { return reply(400, { error: "invalid_json" }); }

  const body = payload.Body && typeof payload.Body === "object"
    ? payload.Body as Record<string, unknown> : {};
  const callback = body.stkCallback && typeof body.stkCallback === "object"
    ? body.stkCallback as Record<string, unknown> : null;
  if (!callback) return reply(400, { error: "invalid_callback_shape" });

  const checkoutId = safeString(callback.CheckoutRequestID, 128);
  const resultCode = Number.isInteger(callback.ResultCode) ? Number(callback.ResultCode) : null;
  const resultDescription = safeString(callback.ResultDesc, 160);
  const metadata = metadataItems(callback.CallbackMetadata);
  const receipt = safeString(metadata.MpesaReceiptNumber, 32);
  const rawAmount = metadata.Amount;
  const amountMinor = typeof rawAmount === "number" && Number.isFinite(rawAmount) && rawAmount > 0
    ? Math.round(rawAmount * 100) : null;
  const phone = typeof metadata.PhoneNumber === "number" || typeof metadata.PhoneNumber === "string"
    ? String(metadata.PhoneNumber) : "";
  const phoneLast4 = /^254[17][0-9]{8}$/.test(phone) ? phone.slice(-4) : null;

  // The callback body is not authenticated by this endpoint. Persist only a hash and
  // redacted fields; do not trust ResultCode to mark a payment successful or credit a ledger.
  const eventHash = await sha256Hex(raw);
  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const { error: insertError } = await supabase.from("infigen_provider_events").upsert({
    provider: "mpesa",
    event_hash: eventHash,
    checkout_request_id: checkoutId,
    result_code: resultCode,
    result_description: resultDescription,
    receipt_reference: receipt,
    amount_minor: amountMinor,
    phone_last4: phoneLast4,
    verification_status: "pending",
    safe_metadata: {
      has_receipt: Boolean(receipt),
      has_amount: amountMinor !== null,
      has_valid_phone: phoneLast4 !== null,
    },
  }, { onConflict: "event_hash", ignoreDuplicates: true });

  if (insertError) return reply(503, { error: "temporarily_unavailable" });

  if (checkoutId) {
    // Regardless of ResultCode, callback arrival is not payment verification.
    // A separate authenticated server reconciliation step must query Daraja and
    // verify checkout ID, amount, shortcode, currency/receipt before finalizing.
    const { error: updateError } = await supabase
      .from("infigen_payment_intents")
      .update({
        status: "callback_received_pending_verification",
        provider_result_code: resultCode,
        provider_result_description: resultDescription,
        provider_receipt: receipt,
        callback_received_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      .eq("provider", "mpesa")
      .eq("provider_checkout_request_id", checkoutId)
      .in("status", ["pending", "provider_accepted", "callback_received_pending_verification", "unknown"]);
    if (updateError) return reply(503, { error: "temporarily_unavailable" });
  }

  // Fast acknowledgement. No ledger entry is posted by this callback handler.
  return reply(200, { ResultCode: 0, ResultDesc: "Accepted for verification" });
});
