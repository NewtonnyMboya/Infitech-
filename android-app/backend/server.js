const express = require('express');
const helmet = require('helmet');
const app = express();
app.use(helmet());
app.use(express.json({ limit: '20kb' }));

// Placeholder only: no payment is initiated or marked paid.
// Add approved Skrill merchant API calls, webhook/status verification,
// authentication, idempotency and persistent ledger before live use.
app.post('/api/transfers', (req, res) => {
  const { recipientEmail, amount, currency = 'KES' } = req.body || {};
  if (typeof recipientEmail !== 'string' || !/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(recipientEmail))
    return res.status(400).json({ error: 'A valid recipient email is required.' });
  if (!Number.isSafeInteger(amount) || amount <= 0 || currency !== 'KES')
    return res.status(400).json({ error: 'A positive whole-number KES amount is required.' });
  return res.status(501).json({ status: 'not_configured', message: 'Skrill integration not configured; no funds moved.' });
});
app.get('/health', (_req, res) => res.json({ ok: true }));
app.listen(process.env.PORT || 8080, () => console.log('API listening'));
