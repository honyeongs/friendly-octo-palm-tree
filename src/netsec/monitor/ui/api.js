let csrf = '';
export function setCsrf(value) { csrf = value || ''; }
export async function api(path, { method = 'GET', body, bearer } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  const response = await fetch(`/api${path}`, { method, credentials: 'same-origin', headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let message = data.detail || '요청을 처리하지 못했습니다.';
    if (Array.isArray(message)) message = message.map(item => `${item.loc.at(-1)}: ${item.msg}`).join('\n');
    const error = new Error(message); error.status = response.status; throw error;
  }
  return data;
}
export function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
