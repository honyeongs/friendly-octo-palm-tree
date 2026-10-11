import { api, setCsrf, download } from './api.js';
import { $, node, submitForm, toast } from './dom.js';
import { sourceForm, userForm, passwordForm } from './forms.js';
import { titles, renderView } from './views.js';
import { openIncident } from './incidents.js';
import { initializeSaasAuth } from './saas-auth.js';
import { inviteForm } from './saas.js';

const catalog = await api('/saas/catalog');
const state = { user: null, sources: [], view: location.hash === '#billing' ? 'saas/billing' : 'incidents', page: 1, setup: false, total: 0, busy: false, generation: 0, catalog };

function showGate() { state.generation++; state.user = null; setCsrf(''); $('#workspace').classList.add('hidden'); $('#gate').classList.remove('hidden'); }
async function gate() {
  showGate(); state.setup = (await api('/setup')).required;
  document.querySelectorAll('.setup-only').forEach(item => item.classList.toggle('hidden', !state.setup));
  document.querySelectorAll('.login-only').forEach(item => item.classList.toggle('hidden', state.setup));
  for (const name of ['organization', 'display_name']) $('#gate-form').elements[name].required = state.setup;
  $('#gate-form').elements.org_id.required = !state.setup;
  $('#gate-form').elements.org_id.value = localStorage.getItem('netsec-org-id') || '';
  $('#gate-form').elements.password.minLength = state.setup ? 12 : 1;
  $('#gate-title').textContent = state.setup ? '첫 조직 설정' : '로그인';
  $('#gate-submit').textContent = state.setup ? '조직·관리자 생성' : '로그인';
}
submitForm($('#gate-form'), async payload => {
  if (state.setup) {
    const result = await api('/setup', { method: 'POST', body: { organization: payload.organization, display_name: payload.display_name, email: payload.email, password: payload.password } });
    payload.org_id = result.org_id; localStorage.setItem('netsec-org-id', result.org_id);
  }
  const user = await api('/login', { method: 'POST', body: { org_id: payload.org_id, email: payload.email, password: payload.password } });
  localStorage.setItem('netsec-org-id', user.org_id); $('#gate-form').elements.password.value = ''; await enter(user);
});

async function enter(user) {
  state.user = user; setCsrf(user.csrf); $('#gate').classList.add('hidden'); $('#workspace').classList.remove('hidden');
  $('#user-name').textContent = user.display_name; $('#user-role').textContent = { admin: '관리자', analyst: '분석가', viewer: '조회자' }[user.role];
  document.querySelectorAll('.admin-only').forEach(element => element.classList.toggle('hidden', user.role !== 'admin'));
  document.querySelectorAll('.saas-only.admin-only').forEach(element => element.classList.toggle('hidden', !catalog.enabled || user.role !== 'admin'));
  document.querySelectorAll('.writer-only').forEach(element => element.classList.toggle('hidden', user.role === 'viewer'));
  await refresh();
  const match = location.hash.match(/^#incidents\/([a-f0-9]{32})$/); if (match) await openIncident(match[1], state, refresh);
}

async function refresh() {
  if (!state.user) return;
  const generation = ++state.generation; const view = state.view; const role = state.user.role; state.busy = true;
  $('#loading').classList.remove('hidden'); $('#refresh').disabled = true;
  try {
    const summary = await api('/summary'); const sources = await api('/sources');
    const params = new URLSearchParams({ page: String(state.page) });
    if (['incidents', 'events'].includes(view)) { params.set('q', $('#search').value); params.set('source_id', $('#source-filter').value); }
    if (view === 'incidents') params.set('status', $('#status-filter').value);
    const data = await api(`/${view}?${params}`);
    if (view === 'users' && catalog.enabled) data.invites = (await api('/saas/invites')).items;
    if (generation !== state.generation || !state.user) return;
    state.sources = sources.items; state.total = data.total || 0;
    $('#org-name').textContent = summary.organization.name;
    $('#metric-active').textContent = summary.incidents.active; $('#metric-high').textContent = summary.incidents.high;
    $('#metric-events').textContent = summary.events.total; $('#metric-sources').textContent = summary.active_sources;
    $('#nav-count').textContent = summary.incidents.active; $('#view-title').textContent = titles[view];
    const filter = $('#source-filter'); const selected = filter.value; filter.replaceChildren(node('option', '모든 소스', { value: '' }));
    state.sources.forEach(source => filter.append(node('option', source.name, { value: source.id }))); filter.value = selected;
    $('#view-caption').textContent = ({ policy: '조직별 탐지 기준과 예외', 'saas/billing': `${data.usage?.month || ''} · UTC 월 기준`, 'saas/health': '수집·작업 처리 현황', 'saas/integrations': '조직별 연결 설정', 'saas/privacy': '조직 데이터 요청' })[view] || `${data.total ?? data.items?.length ?? 0}개 항목 · 한국 시간`;
    $('#filters').classList.toggle('hidden', !['incidents', 'events'].includes(view));
    $('#status-filter').classList.toggle('hidden', view !== 'incidents');
    $('#create-source').classList.toggle('hidden', view !== 'sources' || role !== 'admin'); $('#create-user').classList.toggle('hidden', view !== 'users' || role !== 'admin');
    document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    $('#content').replaceChildren(renderView(view, data, state, refresh));
    $('#pagination').classList.toggle('hidden', !data.page_size || !data.total);
    $('#page-info').textContent = `${state.page} / ${Math.max(1, Math.ceil(state.total / 50))} 페이지 · 총 ${state.total}개`;
    $('#prev-page').disabled = state.page <= 1; $('#next-page').disabled = state.page * 50 >= state.total;
    $('#updated-at').textContent = new Date().toLocaleTimeString('ko-KR', { hour12: false }) + ' 갱신';
  } catch (error) {
    if (generation !== state.generation) return;
    if (error.status === 401) { await gate(); toast('로그인이 만료되었습니다.', true); }
    else $('#content').replaceChildren(node('div', error.message, { class: 'page-error', role: 'alert' }));
  } finally {
    if (generation === state.generation) { state.busy = false; $('#loading').classList.add('hidden'); $('#refresh').disabled = false; }
  }
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', async () => { state.view = button.dataset.view; state.page = 1; await refresh(); }));
$('#filters').addEventListener('submit', async event => { event.preventDefault(); state.page = 1; await refresh(); });
$('#refresh').addEventListener('click', refresh);
$('#prev-page').addEventListener('click', async () => { if (state.page > 1) state.page--; await refresh(); });
$('#next-page').addEventListener('click', async () => { state.page++; await refresh(); });
$('#create-source').addEventListener('click', () => sourceForm(refresh));
$('#create-user').addEventListener('click', () => catalog.enabled ? inviteForm(refresh) : userForm(refresh));
$('#password-open').addEventListener('click', () => passwordForm(gate));
$('#logout').addEventListener('click', async () => { try { await api('/logout', { method: 'POST', body: {} }); state.view = 'incidents'; state.page = 1; await gate(); } catch (error) { toast(error.message, true); } });
$('#export').addEventListener('click', async () => { try { download(await api('/export'), 'netsec-incidents.json'); } catch (error) { toast(error.message, true); } });
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.close).close()));
$('#form-dialog').addEventListener('close', () => { if (!$('#form-dialog').open) $('#form-content').replaceChildren(); });
setInterval(() => { if (state.user && !state.busy && !document.hidden && !document.querySelector('dialog[open]') && !['policy', 'saas/integrations'].includes(state.view)) refresh(); }, 15000);
try { const user = await api('/me'); await enter(user); } catch { await gate(); }
initializeSaasAuth(catalog);
