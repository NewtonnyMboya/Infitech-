import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const headers = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "POST, OPTIONS", "Content-Type": "application/json" };
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers });
const env = (key: string) => Deno.env.get(key)?.trim() ?? "";

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers });
  if (req.method !== "POST") return reply({ error: "method_not_allowed" }, 405);
  const url = env("SUPABASE_URL"), serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceKey) return reply({ error: "server_configuration_missing" }, 503);

  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return reply({ error: "invalid_json" }, 400); }
  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

  // Callbacks are untrusted notifications, not proof of settlement. Store a bounded payload for reconciliation only.
  const stk = (body as any)?.Body?.stkCallback;
  const stkId = typeof stk?.CheckoutRequestID === "string" ? stk.CheckoutRequestID : null;
  const b2c = body as any;
  const b2cResult = b2c?.Result ?? b2c;
  const b2cId = typeof b2cResult?.OriginatorConversationID === "string" ? b2cResult.OriginatorConversationID : null;
  const receipt = stkId || b2cId;
  if (!receipt) return reply({ ResultCode: 0, ResultDesc: "Callback received; no matching request identifier" });

  const serialized = JSON.stringify(body);
  const safePayload = serialized.length <= 12000 ? body : { truncated: true, preview: serialized.slice(0, 11000) };
  let query = admin.from("infigen_provider_payment_requests").update({
    status: "callback_received", callback_payload: safePayload,
    callback_received_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  });
  query = stkId ? query.eq("provider_request_id", stkId) : query.eq("provider_conversation_id", b2cId);
  const { error } = await query;
  if (error) return reply({ error: "callback_recording_failed" }, 500);

  // Intentionally no ledger update, balance change, or success claim here.
  return reply({ ResultCode: 0, ResultDesc: "Callback recorded for independent reconciliation; no balance changed" });
});
