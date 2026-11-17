const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../assets/supabase-cloud.js'), 'utf8');
const calls = []; let schoolRows = []; let membershipRows = [];
const response = (data, ok = true, status = 200) => ({ ok, status, json: async () => data });
const window = { SUPABASE_CONFIG: { url: 'https://project.supabase.co', publishableKey: 'sb_publishable_test' }, fetch: async (url, options = {}) => {
  calls.push({ url, options });
  if (url.includes('/auth/v1/signup')) return response({ user: { id: 'user-1', email: 'admin@example.test' } });
  if (url.includes('/auth/v1/token?grant_type=password')) return response({ access_token: 'ephemeral-test-token', user: { id: 'user-1', email: 'admin@example.test' } });
  if (url.includes('/school_member_roles?')) return response(membershipRows);
  if (url.includes('/rest/v1/schools?')) return response(schoolRows);
  if (url.includes('/rpc/create_school')) { schoolRows = [{ id: 'school-1', name: 'Test School', school_code: 'TST', county: 'Nairobi', currency_code: 'KES' }]; membershipRows = [{ school_id: 'school-1', role: 'admin' }]; return response('school-1'); }
  if (url.includes('/rpc/add_school_member') || url.includes('/auth/v1/logout')) return response(null);
  throw new Error('Unexpected request: ' + url);
} };
const document = { readyState: 'loading', addEventListener() {} };
vm.runInNewContext(source, { window, document, Map, Object, Array, String, RegExp, Error, JSON, Date });
(async () => {
  const api = window.SchoolCoreCloud;
  const signup = await api.signUp('Admin Person', 'ADMIN@example.test', 'strong-pass-123');
  assert.equal(signup.confirmationRequired, true);
  assert.equal(api.getState().signedIn, false);
  await api.signIn('admin@example.test', 'strong-pass-123');
  const school = await api.createSchool('Test School', 'TST', 'Nairobi');
  assert.equal(school.id, 'school-1');
  assert.equal(api.getState().activeSchool.role, 'admin');
  await api.addMember('teacher@example.test', 'teacher');
  await assert.rejects(() => api.addMember('bad@example.test', 'superuser'), /permitted staff role/);
  await api.signOut(); assert.equal(api.getState().signedIn, false);
  console.log('PASS: signup, sign-in, school creation, first-admin role, staff role validation, sign-out');
})().catch(err => { console.error(err); process.exitCode = 1; });
