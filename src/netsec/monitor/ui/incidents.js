import { api } from './api.js';
import { $, node, badge, paired, formatTime, table, cells, select, labels, submitForm, toast } from './dom.js';
import { finishForm } from './forms.js';

let requestVersion = 0;
function busy(value) {
  $('#detail-content').setAttribute('aria-busy', String(value));
  $('#detail-content').querySelectorAll('button,input,select,textarea').forEach(control => { control.disabled = value; });
}
$('#detail-dialog').addEventListener('close', () => { requestVersion++; });

async function mutate(task) {
  busy(true);
  try { await task(); } finally { busy(false); }
}

export async function openIncident(id, state, refresh) {
  const version = ++requestVersion;
  busy(true);
  try {
    const item = await api(`/incidents/${id}`); const users = (await api('/users')).items;
    if (version !== requestVersion) return;
    const dialog = $('#detail-dialog'); $('#detail-title').textContent = item.title;
    const content = node('div'); const details = node('dl', null, { class: 'detail-grid' });
    const source = state.sources.find(source => source.id === item.source_id);
    for (const [title, value] of [['위험도', labels[item.severity]], ['상태', labels[item.status]], ['연결 소스', source?.name || item.source_id], ['출발 IP', item.source_ip], ['사용자', item.username || '여러 사용자'], ['최초 관측 · KST', formatTime(item.first_seen)], ['마지막 관측 · KST', formatTime(item.last_seen)], ['호스트', item.evidence[0]?.host || '—'], ['근거 수', String(item.evidence.length)]]) {
      const pair = node('div'); pair.append(node('dt', title), node('dd', value)); details.append(pair);
    }
    content.append(details, node('p', '인증 패턴에 대한 검토 항목입니다. 침해 여부를 확정한 결과는 아닙니다.', { class: 'notice' }));
    if (state.user.role !== 'viewer') {
      const form = node('form', null, { class: 'form-row' });
      form.append(select('처리 상태', 'status', ['open', 'investigating', 'resolved', 'false_positive'].map(key => [key, labels[key]]), item.status),
        select('담당자', 'assignee_id', [['', '미지정'], ...users.filter(user => user.active && user.role !== 'viewer').map(user => [user.id, user.display_name])], item.assignee_id || ''), node('button', '변경 저장', { type: 'submit', class: 'primary' }));
      submitForm(form, async payload => mutate(async () => { await api(`/incidents/${id}`, { method: 'PATCH', body: { ...payload, version: item.version, assignee_id: payload.assignee_id || null } }); toast('처리 상태를 저장했습니다.'); if ($('#detail-dialog').open) await openIncident(id, state, refresh); await refresh(); })); content.append(form);
    }
    content.append(node('h3', '인증 근거 · 한국 시간'), table(['시각', '사용자', '결과', '인증 방식'], item.evidence.slice(0, 200).map(event => cells([formatTime(event.timestamp), event.username, badge(event.outcome === 'failed' ? 'failure' : 'success'), event.method]))));
    if (item.evidence.length > 200) content.append(node('p', `근거 ${item.evidence.length}개 중 200개 표시`, { class: 'secondary' }));
    content.append(node('h3', `조사 메모 ${item.comments.length}`));
    for (const comment of item.comments) { const block = node('div', null, { class: 'comment' }); block.append(paired(comment.author, formatTime(comment.created_at)), node('p', comment.body)); content.append(block); }
    if (state.user.role !== 'viewer') {
      const form = node('form', null, { class: 'stack' }); const label = node('label', '조사 메모'); label.append(node('textarea', null, { name: 'body', required: true, maxlength: 2000, 'aria-label': '조사 메모' })); form.append(label); finishForm(form, '메모 등록');
      submitForm(form, async payload => mutate(async () => { await api(`/incidents/${id}/comments`, { method: 'POST', body: payload }); if ($('#detail-dialog').open) await openIncident(id, state, refresh); })); content.append(form);
    }
    $('#detail-content').replaceChildren(content); if (!dialog.open) dialog.showModal();
  } catch (error) { toast(error.message, true); }
  finally { if (version === requestVersion) busy(false); }
}
