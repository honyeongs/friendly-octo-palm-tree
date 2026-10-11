import { api } from './api.js';
import { $, node, field, select, submitForm, toast } from './dom.js';

export function modal(title, content) {
  const dialog = $('#form-dialog'); $('#form-title').textContent = title; $('#form-content').replaceChildren(content);
  if (!dialog.open) dialog.showModal();
}
export function closeForm() { $('#form-dialog').close(); $('#form-content').replaceChildren(); }
export function formShell() {
  const form = node('form', null, { class: 'stack' }); return form;
}
export function finishForm(form, text) { form.append(node('p', '', { class: 'error', role: 'alert' }), node('button', text, { type: 'submit', class: 'primary' })); }

export function sourceForm(refresh) {
  const form = formShell(); form.append(field('소스 이름', 'name', 'text', '', { required: true, maxlength: 100 }), select('종류', 'kind', [['app', '웹·모바일 앱'], ['ssh', 'SSH 서버']]));
  finishForm(form, '소스 생성');
  submitForm(form, async payload => {
    const result = await api('/sources', { method: 'POST', body: payload });
    const content = node('div', null, { class: 'stack' });
    content.append(node('p', '수집 키는 지금 한 번만 표시됩니다. 안전한 비밀 저장소에 보관하세요.', { class: 'notice' }), node('pre', result.token, { class: 'secret', id: 'source-token' }));
    const copy = node('button', '수집 키 복사'); copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(result.token); toast('복사했습니다.'); } catch { toast('이 브라우저에서 복사 권한을 사용할 수 없습니다.', true); } }); content.append(copy);
    if (payload.kind === 'app') {
      const sample = node('button', '합성 인증 이벤트 6개 보내기', { id: 'sample-events' });
      sample.addEventListener('click', async () => {
        sample.disabled = true;
        try {
          const clock = Date.now() - 60000; const group = crypto.randomUUID();
          const events = Array.from({ length: 6 }, (_, index) => ({ event_id: `${group}-${index}`, timestamp: new Date(clock + index * 5000).toISOString(), outcome: index === 5 ? 'success' : 'failure', username: 'demo-user', source_ip: '192.0.2.25', host: 'synthetic-demo', method: 'password', event_type: 'auth.login' }));
          await api('/v1/events', { method: 'POST', body: { events }, bearer: result.token });
          toast('합성 이벤트 6개를 수집했습니다.'); await refresh();
        } catch (error) { toast(error.message, true); sample.disabled = false; }
      }); content.append(sample);
    }
    content.append(node('p', `소스 ID: ${result.id}`, { class: 'secondary' }));
    modal('수집 키', content); await refresh();
  }); modal('연결 소스 추가', form);
}

export function userForm(refresh) {
  const form = formShell(); form.append(field('이름', 'display_name', 'text', '', { required: true, maxlength: 80 }), field('이메일', 'email', 'email', '', { required: true, maxlength: 254 }), field('초기 비밀번호', 'password', 'password', '', { required: true, minlength: 12, maxlength: 256, autocomplete: 'new-password' }), select('역할', 'role', [['viewer', '조회자'], ['analyst', '분석가'], ['admin', '관리자']]));
  finishForm(form, '사용자 추가'); submitForm(form, async payload => { await api('/users', { method: 'POST', body: payload }); closeForm(); toast('사용자를 추가했습니다.'); await refresh(); }); modal('사용자 추가', form);
}

export function userEditForm(item, refresh) {
  const form = formShell(); form.append(select('역할', 'role', [['viewer', '조회자'], ['analyst', '분석가'], ['admin', '관리자']], item.role), select('계정 상태', 'active', [['true', '활성'], ['false', '사용 중지']], String(Boolean(item.active))));
  finishForm(form, '변경 저장'); submitForm(form, async payload => { await api(`/users/${item.id}`, { method: 'PATCH', body: { role: payload.role, active: payload.active === 'true' } }); closeForm(); toast('변경했습니다. 기존 로그인 세션은 해제됩니다.'); await refresh(); }); modal(item.display_name, form);
}

export function passwordForm(onSuccess) {
  const form = formShell(); form.append(field('현재 비밀번호', 'current_password', 'password', '', { required: true, autocomplete: 'current-password' }), field('새 비밀번호', 'new_password', 'password', '', { required: true, minlength: 12, maxlength: 256, autocomplete: 'new-password' }));
  finishForm(form, '비밀번호 변경'); submitForm(form, async payload => { await api('/password', { method: 'POST', body: payload }); closeForm(); toast('비밀번호를 변경했습니다. 다시 로그인하세요.'); onSuccess(); }); modal('비밀번호 변경', form);
}
