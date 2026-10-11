import { api } from './api.js';
import { $, node, field, select, submitForm, toast } from './dom.js';
import { modal, formShell, finishForm } from './forms.js';

function message(text) { modal('안내', node('p', text, { class: 'notice' })); }

export function initializeSaasAuth(catalog) {
  document.querySelectorAll('.saas-only:not(.admin-only)').forEach(item => item.classList.toggle('hidden', !catalog.enabled));
  $('#signup-open').addEventListener('click', () => {
    const form = formShell();
    form.append(field('회사 이름', 'organization', 'text', '', { required: true, maxlength: 100 }),
      field('관리자 이름', 'display_name', 'text', '', { required: true, maxlength: 80 }),
      field('이메일', 'email', 'email', '', { required: true, maxlength: 254, autocomplete: 'email' }),
      field('비밀번호', 'password', 'password', '', { required: true, minlength: 12, maxlength: 256, autocomplete: 'new-password' }));
    if (!catalog.public_launch) form.append(node('p', '개발용 가입 환경입니다. 실제 결제는 발생하지 않습니다.', { class: 'notice' }));
    const agree = node('label', null, { class: 'checkbox-label' });
    agree.append(node('input', null, { type: 'checkbox', name: 'accepted_terms', required: true }), node('span', `이용약관 및 개인정보 안내 확인 (${catalog.terms_version})`));
    const links = node('div');
    links.append(node('a', '이용약관', { href: catalog.terms_url || '/legal/terms', target: '_blank', rel: 'noopener' }), node('span', ' · '), node('a', '개인정보 안내', { href: catalog.privacy_url || '/legal/privacy', target: '_blank', rel: 'noopener' }));
    form.append(links, agree); finishForm(form, '14일 체험 가입');
    submitForm(form, async payload => {
      const result = await api('/saas/signup', { method: 'POST', body: { ...payload, accepted_terms: payload.accepted_terms === 'on', terms_version: catalog.terms_version } });
      message(result.message);
    }); modal('회사 계정 만들기', form);
  });
  $('#reset-open').addEventListener('click', () => {
    const form = formShell(); form.append(field('조직 ID', 'org_id', 'text', localStorage.getItem('netsec-org-id') || '', { required: true, maxlength: 64 }), field('이메일', 'email', 'email', '', { required: true, maxlength: 254 }), select('요청', 'purpose', [['reset', '비밀번호 재설정'], ['verify', '가입 확인 메일 재발송']]));
    finishForm(form, '안내 메일 요청'); submitForm(form, async ({ purpose, ...body }) => message((await api(`/saas/email?purpose=${purpose}`, { method: 'POST', body })).message)); modal('계정 복구', form);
  });
  $('#sso-open').addEventListener('click', () => {
    const value = $('#gate-form').elements.org_id.value.trim();
    if (!value) return toast('조직 ID를 입력하세요.', true);
    location.assign(`/api/saas/sso/start?org_id=${encodeURIComponent(value)}`);
  });
  $('#dev-mail').classList.toggle('hidden', !catalog.local_mail);
  $('#dev-mail').addEventListener('click', async () => {
    try {
      const data = await api('/saas/dev-mail'); const content = node('div', null, { class: 'stack' });
      for (const item of data.items) {
        const section = node('section'); section.append(node('h3', item.recipient), node('pre', item.body, { class: 'secret' }));
        const match = item.body.match(/#action\/([\w-]+)/); if (match) { const open = node('button', '링크 열기'); open.addEventListener('click', () => actionForm(match[1])); section.append(open); }
        content.append(section);
      }
      if (!data.items.length) content.append(node('p', '대기 중인 메일이 없습니다.'));
      modal('로컬 테스트 메일', content);
    } catch (error) { toast(error.message, true); }
  });
  function actionForm(token) {
    history.replaceState(null, '', '/');
    const form = formShell();
    form.append(field('이름 (초대 수락 시)', 'display_name', 'text', '', { maxlength: 80 }), field('새 비밀번호 (초대·복구 시)', 'password', 'password', '', { maxlength: 256, autocomplete: 'new-password' }));
    finishForm(form, '이메일 확인·요청 완료'); submitForm(form, async payload => {
      const result = await api('/saas/consume', { method: 'POST', body: { ...payload, token } });
      localStorage.setItem('netsec-org-id', result.org_id); $('#gate-form').elements.org_id.value = result.org_id;
      message(`${result.message}\n조직 ID: ${result.org_id}`);
    }); modal('계정 요청 확인', form);
  }
  const action = location.hash.match(/^#action\/([\w-]+)$/); if (action && catalog.enabled) actionForm(action[1]);
}
