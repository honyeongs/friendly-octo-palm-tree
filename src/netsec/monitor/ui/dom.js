export const $ = selector => document.querySelector(selector);
export function node(tag, text, attrs = {}) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') element.className = value;
    else element.setAttribute(key, String(value));
  }
  return element;
}
export function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Seoul' }).format(date);
}
export const labels = { open: '신규', investigating: '조사 중', resolved: '해결', false_positive: '오탐', high: '높음', medium: '중간',
  failure: '실패', success: '성공', failed: '전송 실패', sent: '완료', skipped: '미설정', pending: '대기', processing: '전송 중',
  admin: '관리자', analyst: '분석가', viewer: '조회자', in_app: '화면 알림', webhook: '웹훅', email: '이메일' };
export function badge(value) { return node('span', labels[value] || value, { class: `badge ${value}` }); }
export function table(headers, rows) {
  const wrap = node('div', null, { class: 'table-wrap' }); const grid = node('table'); const head = node('thead'); const tr = node('tr');
  headers.forEach(header => tr.append(node('th', header))); head.append(tr); grid.append(head);
  const body = node('tbody'); rows.forEach(row => body.append(row)); grid.append(body); wrap.append(grid); return wrap;
}
export function cells(values, onClick) {
  const tr = node('tr');
  values.forEach(value => { const td = node('td'); td.append(value instanceof Node ? value : document.createTextNode(String(value ?? '—'))); tr.append(td); });
  if (onClick) { tr.className = 'clickable'; tr.tabIndex = 0; tr.setAttribute('role', 'button'); tr.addEventListener('click', onClick); tr.addEventListener('keydown', event => { if (event.key === 'Enter') onClick(); }); }
  return tr;
}
export function paired(main, sub) { const block = node('div'); block.append(node('strong', main), node('span', sub, { class: 'secondary' })); return block; }
export function field(label, name, type = 'text', value = '', attrs = {}) {
  const wrapper = node('label', label); const input = node('input', null, { name, type, ...attrs }); input.value = value; wrapper.append(input); return wrapper;
}
export function select(label, name, options, value = '') {
  const wrapper = node('label', label); const input = node('select', null, { name });
  options.forEach(([key, title]) => input.append(node('option', title, { value: key }))); input.value = value === '' ? (options[0]?.[0] ?? '') : value; wrapper.append(input); return wrapper;
}
export function empty(title, subtitle) {
  const block = node('div', null, { class: 'empty' }); block.append(node('img', null, { src: '/assets/shield-check.svg', alt: '' }), node('h3', title), node('p', subtitle)); return block;
}
export function toast(message, bad = false) {
  const area = $('#toast'); area.textContent = message; area.className = `toast${bad ? ' bad' : ''}`;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => area.classList.add('hidden'), 6000);
}
export function submitForm(form, handler) {
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('[type="submit"]'); const error = form.querySelector('.error');
    if (button) button.disabled = true; if (error) error.textContent = '';
    try { await handler(Object.fromEntries(new FormData(form))); }
    catch (failure) { if (error) error.textContent = failure.message; else toast(failure.message, true); }
    finally { if (button) button.disabled = false; }
  });
}
