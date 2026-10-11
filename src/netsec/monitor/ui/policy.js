import { api } from './api.js';
import { node, field, select, formatTime, submitForm, toast } from './dom.js';
import { finishForm } from './forms.js';

export function policyView(data, sources, refresh) {
  const root = node('div', null, { class: 'settings-layout' }); const section = node('section'); section.append(node('h2', '탐지 기준'));
  const form = node('form', null, { class: 'policy-form' });
  form.append(field('실패 횟수', 'threshold', 'number', data.threshold, { required: true, min: 2, max: 100 }), field('실패 관측 구간 · 초', 'window_seconds', 'number', data.window_seconds, { required: true, min: 10, max: 3600 }), field('성공 연결 구간 · 초', 'success_seconds', 'number', data.success_seconds, { required: true, min: 10, max: 3600 }), field(`알림 이메일 · SMTP ${data.email_available ? '연결됨' : '미설정'}`, 'notification_email', 'email', data.notification_email, { maxlength: 254 }));
  const webhook = node('label', `웹훅 알림 · ${data.webhook_available ? '연결됨' : '미설정'}`, { class: 'checkbox-label' }); const check = node('input', null, { type: 'checkbox', name: 'webhook_enabled' }); check.checked = Boolean(data.webhook_enabled); webhook.prepend(check); form.append(webhook);
  const action = node('div', null, { class: 'full' }); action.append(node('button', '정책 저장', { type: 'submit', class: 'primary' })); form.append(action);
  submitForm(form, async payload => { await api('/policy', { method: 'PUT', body: { threshold: Number(payload.threshold), window_seconds: Number(payload.window_seconds), success_seconds: Number(payload.success_seconds), notification_email: payload.notification_email, webhook_enabled: check.checked } }); toast('정책을 저장했습니다. 다음 수집부터 적용됩니다.'); await refresh(); }); section.append(form); root.append(section);
  const exclusions = node('section'); exclusions.append(node('h2', '기간 제한 예외'));
  const activeSources = sources.filter(source => source.active);
  if (activeSources.length) {
    const form = node('form', null, { class: 'policy-form' }); form.append(select('연결 소스', 'source_id', activeSources.map(source => [source.id, source.name])), field('IP 또는 CIDR', 'cidr', 'text', '', { required: true, maxlength: 50, placeholder: '192.0.2.25/32' }), field('만료 시각 · 이 기기 시간', 'expires_at', 'datetime-local', '', { required: true }), field('예외 사유', 'reason', 'text', '', { required: true, maxlength: 200 }));
    const footer = node('div', null, { class: 'full' }); footer.append(node('button', '예외 추가', { type: 'submit' })); form.append(footer);
    submitForm(form, async payload => { await api('/exclusions', { method: 'POST', body: { ...payload, expires_at: new Date(payload.expires_at).toISOString() } }); toast('예외를 추가했습니다.'); await refresh(); }); exclusions.append(form);
  }
  for (const item of data.exclusions) {
    const line = node('div', null, { class: 'list-line' }); const text = node('div'); text.append(node('strong', item.cidr), node('span', `${sources.find(source => source.id === item.source_id)?.name || item.source_id} · ${item.reason} · ${formatTime(item.expires_at)} 만료`, { class: 'secondary' }));
    const remove = node('button', '예외 삭제', { class: 'danger' }); remove.addEventListener('click', async () => { try { await api(`/exclusions/${item.id}`, { method: 'DELETE', body: {} }); await refresh(); } catch (error) { toast(error.message, true); } }); line.append(text, remove); exclusions.append(line);
  }
  root.append(exclusions); const retention = node('section'); retention.append(node('h2', '데이터 보관'), node('p', `현재 보관 정책: ${data.retention_days}일`)); root.append(retention); return root;
}
