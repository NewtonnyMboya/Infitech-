'use strict';
const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '32kb' }));
const ROOT = __dirname;
const DATA_DIR = process.env.DATA_DIR || path.resolve(ROOT, '..', 'infigen-private-data');
const FILE_DIR = path.join(DATA_DIR, 'files');
const PRODUCTS_FILE = path.join(DATA_DIR, 'products.json');
const ORDERS_FILE = path.join(DATA_DIR, 'orders.json');
fs.mkdirSync(FILE_DIR, { recursive: true, mode: 0o700 });
if (!fs.existsSync(PRODUCTS_FILE)) fs.writeFileSync(PRODUCTS_FILE, '[]\n');
if (!fs.existsSync(ORDERS_FILE)) fs.writeFileSync(ORDERS_FILE, '[]\n', { mode: 0o600 });
app.use((req,res,next)=>{res.set('X-Content-Type-Options','nosniff');res.set('Referrer-Policy','strict-origin-when-cross-origin');res.set('X-Frame-Options','DENY');next();});
app.use(express.static(path.join(ROOT, 'public'), { index: 'index.html', dotfiles: 'deny', setHeaders(res, file) { if (file.endsWith('.json')) res.setHeader('Cache-Control','no-store'); } }));
const requiredEnv = ['MPESA_CONSUMER_KEY','MPESA_CONSUMER_SECRET','MPESA_SHORTCODE','MPESA_PASSKEY','MPESA_CALLBACK_URL'];
const isProd = process.env.NODE_ENV === 'production';
const env = process.env.MPESA_ENVIRONMENT || 'sandbox';
const baseUrl = env === 'production' ? 'https://api.safaricom.co.ke' : 'https://sandbox.safaricom.co.ke';
const readJson = file => JSON.parse(fs.readFileSync(file,'utf8'));
function writeJsonAtomic(file, data) { const tmp = file + '.' + process.pid + '.tmp'; fs.writeFileSync(tmp, JSON.stringify(data,null,2)+'\n',{mode:0o600}); fs.renameSync(tmp,file); }
function products() { return readJson(PRODUCTS_FILE).filter(p=>p.active === true); }
function publicProduct(p) { const { id,name,category,description,priceKes,image,licenseRequired,version,compatibility } = p; return { id,name,category,description,priceKes,image,licenseRequired:!!licenseRequired,version:version||'',compatibility:compatibility||'' }; }
function getOrders() { return readJson(ORDERS_FILE); }
function saveOrders(orders) { writeJsonAtomic(ORDERS_FILE,orders); }
function randomToken(bytes=32) { return crypto.randomBytes(bytes).toString('base64url'); }
function hashToken(token) { return crypto.createHash('sha256').update(token).digest('hex'); }
function constantEqual(a,b) { const aa=Buffer.from(String(a||'')); const bb=Buffer.from(String(b||'')); return aa.length===bb.length && crypto.timingSafeEqual(aa,bb); }
app.get('/api/health', (_req,res)=>res.json({ok:true,service:'InfiGen',environment:env,catalogProducts:products().length,checkoutEnabled:!!process.env.MPESA_CONSUMER_KEY&&!!process.env.MPESA_CONSUMER_SECRET&&!!process.env.MPESA_SHORTCODE&&!!process.env.MPESA_PASSKEY&&!!process.env.MPESA_CALLBACK_URL}));
app.get('/api/products', (_req,res)=>res.set('Cache-Control','no-store').json(products().map(publicProduct)));
function getTimestamp() { const parts = new Intl.DateTimeFormat('en-GB',{timeZone:'Africa/Nairobi',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date()); const v=Object.fromEntries(parts.map(p=>[p.type,p.value])); return v.year+v.month+v.day+v.hour+v.minute+v.second; }
async function getAccessToken() { const credentials=Buffer.from(`${process.env.MPESA_CONSUMER_KEY}:${process.env.MPESA_CONSUMER_SECRET}`).toString('base64'); const r=await fetch(`${baseUrl}/oauth/v1/generate?grant_type=client_credentials`,{headers:{Authorization:`Basic ${credentials}`},signal:AbortSignal.timeout(15000)}); const d=await r.json(); if(!r.ok||!d.access_token) throw new Error('Daraja authentication failed'); return d.access_token; }
async function darajaPost(endpoint, payload) { const token=await getAccessToken(); const r=await fetch(`${baseUrl}${endpoint}`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(20000)}); const d=await r.json().catch(()=>({})); if(!r.ok) { console.error('Daraja request rejected',r.status); throw new Error('Payment provider rejected request'); } return d; }
function validCallbackUrl() { try { return new URL(process.env.MPESA_CALLBACK_URL).protocol === 'https:'; } catch { return false; } }
app.post('/api/checkout', async (req,res)=>{
  const missing=requiredEnv.filter(k=>!process.env[k]);
  if(missing.length||!validCallbackUrl()) return res.status(503).json({error:'Payment service is not configured for testing',missing});
  if(env!=='sandbox' && process.env.ALLOW_LIVE_PAYMENTS!=='true') return res.status(503).json({error:'Live payments are disabled until explicitly enabled after production verification.'});
  const {items,email,phoneNumber}=req.body||{};
  if(!Array.isArray(items)||items.length<1||items.length>20) return res.status(400).json({error:'Cart must contain 1–20 product lines'});
  if(typeof email!=='string'||email.length>254||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return res.status(400).json({error:'Enter a valid email address'});
  if(!/^254[17]\d{8}$/.test(String(phoneNumber||''))) return res.status(400).json({error:'Use a Kenyan mobile number in 254XXXXXXXXX format'});
  const catalog=products(); const lines=[];
  for(const line of items) { const p=catalog.find(x=>x.id===line.id); const quantity=Number(line.quantity); if(!p||!Number.isSafeInteger(quantity)||quantity<1||quantity>5) return res.status(400).json({error:'A cart item is invalid or unavailable'}); lines.push({productId:p.id,name:p.name,unitPriceKes:p.priceKes,quantity,licenseRequired:!!p.licenseRequired,fileName:p.fileName||null}); }
  const amount=lines.reduce((sum,l)=>sum+l.unitPriceKes*l.quantity,0);
  if(!Number.isSafeInteger(amount)||amount<1||amount>150000) return res.status(400).json({error:'Order total is outside the supported payment range'});
  const orderId='IG'+crypto.randomBytes(5).toString('hex').toUpperCase(); const accessToken=randomToken();
  const order={id:orderId,createdAt:new Date().toISOString(),email,phoneNumber,items:lines,amountKes:amount,currency:'KES',status:'payment_pending',paymentProvider:'mpesa-daraja',environment:env,accessTokenHash:hashToken(accessToken),checkoutRequestId:null,merchantRequestId:null,receipt:null,paidAt:null,entitlements:[],callbackResult:null};
  const orders=getOrders(); orders.push(order); saveOrders(orders);
  try {
    const timestamp=getTimestamp(), shortcode=process.env.MPESA_SHORTCODE;
    const password=Buffer.from(shortcode+process.env.MPESA_PASSKEY+timestamp).toString('base64');
    const result=await darajaPost('/mpesa/stkpush/v1/processrequest',{BusinessShortCode:shortcode,Password:password,Timestamp:timestamp,TransactionType:process.env.MPESA_TRANSACTION_TYPE||'CustomerPayBillOnline',Amount:amount,PartyA:phoneNumber,PartyB:shortcode,PhoneNumber:phoneNumber,CallBackURL:process.env.MPESA_CALLBACK_URL,AccountReference:orderId,TransactionDesc:'InfiGen digital order'});
    const fresh=getOrders(), stored=fresh.find(o=>o.id===orderId); stored.checkoutRequestId=result.CheckoutRequestID||null; stored.merchantRequestId=result.MerchantRequestID||null; stored.providerResponseCode=result.ResponseCode||null; saveOrders(fresh);
    if(result.ResponseCode!=='0') return res.status(502).json({error:result.ResponseDescription||'Could not initiate M-Pesa payment',orderId,accessToken});
    return res.status(201).json({orderId,accessToken,status:'payment_pending',message:result.CustomerMessage||'Check your phone and complete the M-Pesa prompt.'});
  } catch(e) { const fresh=getOrders(), stored=fresh.find(o=>o.id===orderId); if(stored) {stored.status='payment_initiation_failed';stored.failureReason='Payment request could not be initiated';saveOrders(fresh);} console.error('Checkout initiation failed:',e.message); return res.status(502).json({error:'Could not start M-Pesa payment. No order has been marked paid.'}); }
});
async function queryStkStatus(order) { if(!order.checkoutRequestId) return null; const timestamp=getTimestamp(), shortcode=process.env.MPESA_SHORTCODE; const password=Buffer.from(shortcode+process.env.MPESA_PASSKEY+timestamp).toString('base64'); return darajaPost('/mpesa/stkpushquery/v1/query',{BusinessShortCode:shortcode,Password:password,Timestamp:timestamp,CheckoutRequestID:order.checkoutRequestId}); }
function fulfil(order, callback) { if(order.status==='paid') return; order.status='paid';order.paidAt=new Date().toISOString();order.callbackResult={resultCode:callback.ResultCode,resultDesc:callback.ResultDesc||''}; const meta=callback.CallbackMetadata?.Item||[]; const receipt=meta.find(x=>x.Name==='MpesaReceiptNumber')?.Value; order.receipt=receipt?String(receipt):null; order.entitlements=[]; for(const item of order.items) for(let i=0;i<item.quantity;i++){const entitlement={productId:item.productId,downloadToken:randomToken(24),downloadExpiresAt:new Date(Date.now()+7*24*3600*1000).toISOString()}; if(item.licenseRequired) entitlement.licenseKey='IG-'+crypto.randomBytes(4).toString('hex').toUpperCase()+'-'+crypto.randomBytes(4).toString('hex').toUpperCase(); order.entitlements.push(entitlement); } }
app.post('/api/mpesa/callback', async (req,res)=>{
  const cb=req.body?.Body?.stkCallback;
  if(!cb||typeof cb.CheckoutRequestID!=='string'||typeof cb.ResultCode!=='number') return res.status(400).json({ResultCode:1,ResultDesc:'Invalid callback payload'});
  let orders=getOrders(), order=orders.find(o=>o.checkoutRequestId===cb.CheckoutRequestID);
  if(!order) { console.warn('Callback for unknown checkout ID'); return res.status(200).json({ResultCode:0,ResultDesc:'Callback acknowledged'}); }
  if(order.status==='paid') return res.status(200).json({ResultCode:0,ResultDesc:'Already processed'});
  if(cb.ResultCode!==0) { order.status='payment_failed';order.callbackResult={resultCode:cb.ResultCode,resultDesc:String(cb.ResultDesc||'')};saveOrders(orders);return res.status(200).json({ResultCode:0,ResultDesc:'Failure recorded'}); }
  try {
    // Callback success is not sufficient on its own: confirm the STK request with Daraja.
    const q=await queryStkStatus(order);
    const meta=cb.CallbackMetadata?.Item||[];
    const callbackAmount=meta.find(x=>x.Name==='Amount')?.Value;
    const callbackPhone=meta.find(x=>x.Name==='PhoneNumber')?.Value;
    const callbackReceipt=meta.find(x=>x.Name==='MpesaReceiptNumber')?.Value;
    const amountMatches=Number(callbackAmount)===order.amountKes;
    const phoneMatches=String(callbackPhone||'')===String(order.phoneNumber);
    const hasReceipt=typeof callbackReceipt==='string' && callbackReceipt.trim().length>0;
    if(q && String(q.ResponseCode)==='0' && String(q.ResultCode)==='0' && amountMatches && phoneMatches && hasReceipt) { fulfil(order,cb); saveOrders(orders); }
    else { order.status='payment_verification_pending';order.callbackResult={resultCode:0,resultDesc:'Payment callback awaits provider, amount, phone and receipt verification'};saveOrders(orders); }
  } catch(e) { order.status='payment_verification_pending';order.callbackResult={resultCode:0,resultDesc:'Provider verification temporarily unavailable'};saveOrders(orders);console.error('Callback verification failed:',e.message); }
  return res.status(200).json({ResultCode:0,ResultDesc:'Callback received'});
});
function authorizeOrder(req, order) { const token=req.get('x-order-access-token')||req.query.accessToken; return !!token&&constantEqual(hashToken(token),order.accessTokenHash); }
app.get('/api/orders/:id', (req,res)=>{ const order=getOrders().find(o=>o.id===req.params.id); if(!order||!authorizeOrder(req,order)) return res.status(404).json({error:'Order not found'}); res.set('Cache-Control','no-store').json({id:order.id,status:order.status,amountKes:order.amountKes,currency:order.currency,createdAt:order.createdAt,paidAt:order.paidAt,receipt:order.receipt,items:order.items.map(({productId,name,quantity})=>({productId,name,quantity})),entitlements:order.status==='paid'?order.entitlements.map(e=>({productId:e.productId,licenseKey:e.licenseKey||null,downloadUrl:e.downloadToken?`/api/download/${order.id}/${e.downloadToken}`:null,downloadExpiresAt:e.downloadExpiresAt||null})):[]}); });
app.get('/api/download/:orderId/:token',(req,res)=>{ const orders=getOrders(),order=orders.find(o=>o.id===req.params.orderId); if(!order||order.status!=='paid') return res.status(404).json({error:'Download unavailable until payment is verified'}); const entitlement=order.entitlements.find(e=>constantEqual(e.downloadToken,req.params.token)); if(!entitlement||!entitlement.downloadExpiresAt||Date.parse(entitlement.downloadExpiresAt)<Date.now()) return res.status(404).json({error:'Download link is invalid or expired'}); const item=order.items.find(i=>i.productId===entitlement.productId); if(!item?.fileName) return res.status(404).json({error:'The seller has not attached a download file for this product'}); const file=path.resolve(FILE_DIR,item.fileName); if(path.dirname(file)!==FILE_DIR||!fs.existsSync(file)||!fs.statSync(file).isFile()) return res.status(404).json({error:'Product file is unavailable'}); res.set('Cache-Control','no-store');res.set('Content-Disposition',`attachment; filename="${path.basename(file).replace(/[\r\n"\\]/g,'_')}"`);return res.sendFile(file); });
app.post('/api/admin/products', (req,res)=>{ const expected=process.env.ADMIN_API_TOKEN; if(!expected||!constantEqual(req.get('x-admin-token'),expected)) return res.status(401).json({error:'Unauthorized'}); const {id,name,category,description,priceKes,image,licenseRequired,fileName,version,compatibility,active,rightsBasis,sourceUrl,licenseUrl,proofReference}=req.body||{}; if(typeof id!=='string'||!/^[a-z0-9][a-z0-9-]{1,59}$/.test(id)||typeof name!=='string'||name.trim().length<2||name.length>120||typeof category!=='string'||category.length>50||typeof description!=='string'||description.length>2000||!Number.isSafeInteger(priceKes)||priceKes<1||priceKes>150000) return res.status(400).json({error:'Provide a product ID, name, category, description, and valid integer priceKes'}); if(active===true){if(!['owned','authorized_reseller','open_source_compliant'].includes(rightsBasis)||typeof sourceUrl!=='string'||!/^https:\/\//.test(sourceUrl)||typeof proofReference!=='string'||proofReference.trim().length<4) return res.status(400).json({error:'To publish a product, provide rightsBasis (owned, authorized_reseller, or open_source_compliant), an HTTPS sourceUrl, and proofReference for ownership, reseller authorization, or license compliance.'});if(rightsBasis==='open_source_compliant'&&(typeof licenseUrl!=='string'||!/^https:\/\//.test(licenseUrl)))return res.status(400).json({error:'Open-source listings require the official HTTPS license URL.'});} if(fileName&&(typeof fileName!=='string'||path.basename(fileName)!==fileName||!/^[-\w.]{1,120}$/.test(fileName))) return res.status(400).json({error:'fileName must be a safe basename in private-data/files'}); if(image&&(!/^https:\/\//.test(image)||image.length>500)) return res.status(400).json({error:'Image must be an HTTPS URL'}); const list=readJson(PRODUCTS_FILE); const idx=list.findIndex(p=>p.id===id); const p={id,name:name.trim(),category,description,priceKes,image:image||'',licenseRequired:!!licenseRequired,fileName:fileName||null,version:version||'',compatibility:compatibility||'',active:active===true,rightsBasis:rightsBasis||'',sourceUrl:sourceUrl||'',licenseUrl:licenseUrl||'',proofReference:proofReference||''}; if(idx>=0) list[idx]=p;else list.push(p);writeJsonAtomic(PRODUCTS_FILE,list);return res.status(201).json({product:publicProduct(p),active:p.active}); });
app.listen(Number(process.env.PORT||3000),'0.0.0.0',()=>console.log(`InfiGen listening on port ${process.env.PORT||3000}; M-Pesa environment=${env}`));
