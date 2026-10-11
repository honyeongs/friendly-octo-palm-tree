import { api, download } from './api.js';
import { node, field, select, submitForm, toast, table, cells, formatTime, paired } from './dom.js';
import { modal, formShell, finishForm, closeForm } from './forms.js';

export const saasTitles = { 'saas/billing': '구독·사용량', 'saas/health': '수집·처리 상태', 'saas/integrations': '외부 연결', 'saas/privacy': '데이터 관리' };
const roles = [['viewer', '조회자'], ['analyst', '분석가'], ['admin', '관리자']];

function command(text, handler, className = '') {
  const button = node('button', text, { class: className }); button.addEventListener('click', async () => { try { await handler(); } catch (error) { toast(error.message, true); } }); return button;
}

function sensitive(title, execute) {
  const form = formShell(); form.append(field('관리자 비밀번호', 'password', 'password', '', { required: true, autocomplete: 'current-password' }));
  finishForm(form, title); submitForm(form, execute); modal(title, form);
}

export function inviteForm(refresh) {
  const form = formShell(); form.append(field('이메일', 'email', 'email', '', { required: true, maxlength: 254 }), select('역할', 'role', roles));
  finishForm(form, '초대 메일 보내기'); submitForm(form, async payload => { await api('/saas/invites', { method: 'POST', body: payload }); closeForm(); toast('초대 메일을 발송 대기열에 등록했습니다.'); await refresh(); }); modal('사용자 초대', form);
}

export function invitations(items, refresh) {
  const section = node('section'); section.append(node('h3', `초대 대기 ${items.length}명`));
  section.append(table(['이메일', '역할', '만료', '관리'], items.map(item => cells([item.email, item.role, formatTime(item.expires_at), command('초대 취소', async () => { await api('/saas/invites', { method: 'DELETE', body: { email: item.email } }); await refresh(); })])))); return section;
}

export function saasView(view, data, refresh, catalog) {
  const root = node('div', null, { class: 'settings-layout saas-layout' });
  if (view === 'saas/billing') {
    const sub = data.subscription; const section = node('section');
    section.append(node('h2', `${sub.plan} · ${sub.status}`), node('p', `이용 종료: ${formatTime(sub.period_end)} · ${sub.cancel_at_end ? '기간 종료 시 해지' : '해지 예약 없음'}`));
    if (data.mode === 'mock') section.append(node('p', '테스트 결제 모드 · 실제 청구 없음', { class: 'notice' }));
    for (const [key, label] of [['events', '이번 달 이벤트'], ['users', '활성 사용자'], ['sources', '활성 소스']]) {
      const row = node('div', null, { class: 'usage-row' }); const progress = node('progress', null, { max: data.limits[key], value: data.usage[key], 'aria-label': label });
      row.append(node('span', label), node('strong', `${data.usage[key].toLocaleString()} / ${data.limits[key].toLocaleString()}`), progress); section.append(row);
    }
    root.append(section);
    const plans = node('section'); plans.append(node('h2', '요금제'));
    for (const item of catalog.items) {
      const line = node('div', null, { class: 'list-line' });
      line.append(paired(item.name, `월 이벤트 ${item.events.toLocaleString()} · 사용자 ${item.users} · 보관 ${item.retention_days}일`), command('선택', () => sensitive('구독 진행', async payload => {
        const result = await api('/saas/billing/checkout', { method: 'POST', body: { ...payload, plan: item.id } });
        closeForm(); if (result.url) location.assign(result.url); else { toast('테스트 결제 요청을 만들었습니다. 확인 후 활성화하세요.'); await refresh(); }
      }))); plans.append(line);
    }
    if (data.pending && data.mode === 'mock') plans.append(command('테스트 결제 확인', () => sensitive('실제 청구 없이 활성화', async payload => { await api('/saas/billing/mock-confirm', { method: 'POST', body: { ...payload, request_id: data.pending.id } }); closeForm(); await refresh(); }), 'primary'));
    plans.append(command('기간 종료 시 해지', () => sensitive('해지 예약', async payload => { await api('/saas/billing/cancel', { method: 'POST', body: payload }); closeForm(); await refresh(); }), 'danger'));
    if (data.mode === 'stripe') plans.append(command('결제·청구서 포털', () => sensitive('결제 포털 열기', async payload => { const result = await api('/saas/billing/portal', { method: 'POST', body: payload }); location.assign(result.url); })));
    root.append(plans); return root;
  }
  if (view === 'saas/health') {
    root.append(node('h2', '연결 상태'), node('p', data.worker_alive ? '작업 처리기 정상' : '작업 처리기 응답 없음', { class: 'notice' }), table(['소스', '상태', '마지막 수집'], data.items.map(item => cells([item.name, item.status === 'stale' ? '수집 지연' : '정상', formatTime(item.last_seen)]))),
      node('h3', `알림 대기 ${data.queue.count}개`), node('p', `가장 오래된 대기: ${formatTime(data.queue.oldest)}`),
      node('h3', '운영 경보'), table(['내용', '발생 시각'], data.alerts.map(item => cells([item.title, formatTime(item.created_at)]))),
      node('h3', '처리 기한'), table(['사건', '기한', '티켓 참조'], data.tasks.map(item => cells([item.title, formatTime(item.due_at), item.ticket_ref || '미연결'])))); return root;
  }
  if (view === 'saas/integrations') {
    const form = formShell();
    form.append(field('웹훅 주소', 'webhook_url', 'url', data.webhook_url, { maxlength: 2000 }), field(data.webhook_token_set ? '웹훅 토큰 (빈칸: 유지)' : '웹훅 토큰', 'webhook_token', 'password', '', { maxlength: 512, autocomplete: 'new-password' }),
      select('OIDC 발급자', 'oidc_issuer', [['', '사용 안 함'], ...data.approved_issuers.map(value => [value, value])], data.oidc_issuer),
      field('OIDC 클라이언트 ID', 'oidc_client_id', 'text', data.oidc_client_id, { maxlength: 200 }), field(data.oidc_client_secret_set ? 'OIDC 비밀 (빈칸: 유지)' : 'OIDC 비밀', 'oidc_client_secret', 'password', '', { maxlength: 512, autocomplete: 'new-password' }));
    for (const [key, label] of [['oidc_require_mfa', 'SSO 로그인에 MFA 증거 필요'], ['sso_required', 'SSO 로그인만 허용']]) {
      const labelNode = node('label', null, { class: 'checkbox-label' }); const checkbox = node('input', null, { name: key, type: 'checkbox' }); checkbox.checked = data[key]; labelNode.append(checkbox, node('span', label)); form.append(labelNode);
    }
    form.append(field('관리자 비밀번호', 'password', 'password', '', { required: true, autocomplete: 'current-password' })); finishForm(form, '연결 설정 저장');
    submitForm(form, async payload => { await api('/saas/integrations', { method: 'PUT', body: { ...payload, webhook_token: payload.webhook_token || null, oidc_client_secret: payload.oidc_client_secret || null, oidc_require_mfa: payload.oidc_require_mfa === 'on', sso_required: payload.sso_required === 'on' } }); toast('연결 설정을 저장했습니다.'); await refresh(); }); root.append(form); return root;
  }
  const section = node('section'); section.append(node('h2', '고객 데이터'), command('데이터 내보내기', () => sensitive('조직 데이터 내보내기', async payload => { const result = await api('/saas/privacy/export', { method: 'POST', body: { ...payload, kind: 'export' } }); download(result, 'netsec-organization.json'); closeForm(); })),
    command('조직 삭제 요청', () => sensitive('삭제 검토 요청', async payload => { const result = await api('/saas/privacy', { method: 'POST', body: { ...payload, kind: 'delete' } }); closeForm(); toast(result.message); await refresh(); }), 'danger'),
    node('p', '삭제 요청은 운영자가 구독·보존 의무·백업 처리 범위를 확인한 뒤 실행합니다.', { class: 'notice' }));
  root.append(section, table(['요청', '상태', '접수 시각'], data.items.map(item => cells([item.kind, item.status, formatTime(item.created_at)])))); return root;
}

export function taskForm(item, refresh) {
  const form = formShell(); form.append(field('처리 기한', 'due_at', 'datetime-local', '', { required: true }), field('외부 티켓 번호·참조', 'ticket_ref', 'text', '', { maxlength: 200 })); finishForm(form, '기한 저장');
  submitForm(form, async payload => { await api(`/saas/incidents/${item.id}/task`, { method: 'PUT', body: { ...payload, version: item.version, due_at: new Date(payload.due_at).toISOString() } }); closeForm(); toast('기한을 저장했습니다.'); await refresh(); }); modal('사건 처리 기한', form);
}
