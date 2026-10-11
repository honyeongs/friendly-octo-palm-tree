import { api } from './api.js';
import { node, badge, cells, table, empty, paired, formatTime, labels, toast } from './dom.js';
import { userEditForm } from './forms.js';
import { openIncident } from './incidents.js';
import { policyView } from './policy.js';
import { saasTitles, saasView, invitations } from './saas.js';

export const titles = { incidents: '탐지 사건', events: '인증 기록', sources: '연결 소스', notifications: '알림', users: '사용자', policy: '정책·예외', audit: '감사 기록', ...saasTitles };
export function renderView(view, data, state, refresh) {
  if (view.startsWith('saas/')) return saasView(view, data, refresh, state.catalog);
  if (view === 'policy') return policyView(data, state.sources, refresh);
  const items = data.items || []; const sourceName = id => state.sources.find(source => source.id === id)?.name || '—';
  if (!items.length) return empty({ incidents: '탐지된 사건이 없습니다', events: '수집된 인증 기록이 없습니다', sources: '연결된 소스가 없습니다', notifications: '알림이 없습니다', audit: '감사 기록이 없습니다' }[view] || '표시할 항목이 없습니다', view === 'incidents' || view === 'events' ? '현재 검색 조건 기준' : '');
  if (view === 'incidents') return table(['사건', '위험도', '출발 IP', '사용자', '마지막 관측 · KST', '상태'], items.map(item => cells([paired(item.title, sourceName(item.source_id)), badge(item.severity), item.source_ip, item.username || '여러 사용자', formatTime(item.last_seen), badge(item.status)], () => openIncident(item.id, state, refresh))));
  if (view === 'events') return table(['시각 · KST', '소스·호스트', '이벤트', '출발 IP', '사용자', '결과'], items.map(item => cells([formatTime(item.timestamp), paired(sourceName(item.source_id), item.host), item.event_type, item.source_ip, item.username, badge(item.outcome)])));
  if (view === 'sources') return table(['소스 이름', '종류', '상태', '마지막 수집 · KST', '관리'], items.map(item => {
    const actions = node('div');
    if (item.active && state.user.role === 'admin') { const revoke = node('button', '키 폐기', { class: 'danger' }); revoke.addEventListener('click', async () => { if (!confirm(`${item.name} 수집 키를 폐기할까요? 이후 새 이벤트를 받을 수 없습니다.`)) return; try { await api(`/sources/${item.id}`, { method: 'DELETE', body: {} }); toast('키를 폐기했습니다.'); await refresh(); } catch (error) { toast(error.message, true); } }); actions.append(revoke); }
    return cells([paired(item.name, item.id), item.kind === 'ssh' ? 'SSH 서버' : '앱', badge(item.active ? 'success' : 'skipped'), formatTime(item.last_seen), actions]);
  }));
  if (view === 'users') { const content = node('div'); content.append(table(['사용자', '이메일', '역할', '계정 상태', '관리'], items.map(item => {
    const actions = node('div'); if (item.id !== state.user.id) { const edit = node('button', '변경'); edit.addEventListener('click', () => userEditForm(item, refresh)); actions.append(edit); }
    return cells([item.display_name, item.email, labels[item.role], item.active ? '활성' : '중지', actions]);
  }))); if (data.invites) content.append(invitations(data.invites, refresh)); return content; }
  if (view === 'notifications') return table(['시각 · KST', '사건', '채널', '상태', '시도', '관리'], items.map(item => {
    const actions = node('div');
    if (state.user.role === 'admin' && ['failed', 'skipped'].includes(item.status)) { const retry = node('button', '재시도'); retry.addEventListener('click', async () => { try { await api(`/notifications/${item.id}/retry`, { method: 'POST', body: {} }); await refresh(); } catch (error) { toast(error.message, true); } }); actions.append(retry); }
    const link = node('button', item.title, { class: 'subtle' }); link.addEventListener('click', () => openIncident(item.incident_id, state, refresh));
    return cells([formatTime(item.created_at), link, labels[item.channel], paired(labels[item.status] || item.status, item.error), item.attempts, actions]);
  }));
  return table(['시각 · KST', '작업', '수행자', '대상', '변경 요약'], items.map(item => cells([formatTime(item.created_at), item.action, item.actor_id, item.target_id || '—', item.detail])));
}
