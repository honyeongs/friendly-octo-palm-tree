import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const moduleName = process.env.NETSEC_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(/^[A-Z]:|^\./i.test(moduleName) ? pathToFileURL(resolve(moduleName)).href : moduleName);
const python = process.env.NETSEC_PYTHON || 'python';
const temporary = await mkdtemp(join(tmpdir(), 'netsec-saas-'));
const server = createServer(); await new Promise(done => server.listen(0, '127.0.0.1', done)); const port = server.address().port; await new Promise(done => server.close(done));
const base = `http://127.0.0.1:${port}`; const password = 'SaaS browser test password!';
await mkdir('saas-results', { recursive: true });
const child = spawn(python, ['run.py', 'monitor', '--port', String(port)], { windowsHide: true, env: { ...process.env, NETSEC_DB: join(temporary, 'saas.sqlite3'), NETSEC_DATABASE_URL: '', NETSEC_ORIGIN: base, NETSEC_SAAS_ENABLED: '1', NETSEC_BILLING_MODE: 'mock', NETSEC_MAIL_MODE: 'local' }, stdio: ['ignore', 'pipe', 'pipe'] });
let logs = ''; child.stderr.on('data', data => { logs += data.toString(); }); let browser;
async function ready() { for (let i = 0; i < 100; i++) { try { if ((await fetch(base + '/healthz')).ok) return; } catch {} await new Promise(done => setTimeout(done, 150)); } throw new Error(logs); }

try {
  await ready(); browser = await chromium.launch({ headless: true }); const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }); const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(base); await page.getByRole('button', { name: '회사 계정 만들기' }).click();
  await page.locator('#form-dialog').getByLabel('회사 이름', { exact: true }).fill('Portfolio Security'); await page.locator('#form-dialog').getByLabel('관리자 이름', { exact: true }).fill('보안 관리자');
  await page.locator('#form-dialog').getByLabel('이메일', { exact: true }).fill('admin@example.test'); await page.locator('#form-dialog').getByLabel('비밀번호', { exact: true }).fill(password);
  await page.locator('[name="accepted_terms"]').check(); await page.getByRole('button', { name: '14일 체험 가입' }).click(); await page.getByText('확인 메일을 보냈습니다. 이메일 확인 후 로그인하세요.').waitFor();
  await page.locator('#form-dialog [aria-label="닫기"]').click(); await page.getByRole('button', { name: '로컬 테스트 메일' }).click(); await page.getByRole('button', { name: '링크 열기' }).first().click();
  await page.getByRole('button', { name: '이메일 확인·요청 완료' }).click(); await page.getByText(/완료했습니다. 조직 ID와 이메일로 로그인하세요./).waitFor(); await page.locator('#form-dialog [aria-label="닫기"]').click();
  await page.locator('#gate-form').getByLabel('이메일', { exact: true }).fill('admin@example.test'); await page.locator('#gate-form').getByLabel('비밀번호', { exact: true }).fill(password); await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.locator('#workspace').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: '구독·사용량', exact: true }).click(); await page.getByRole('heading', { name: 'starter · trialing' }).waitFor();
  await page.locator('.list-line').filter({ hasText: 'Team' }).getByRole('button', { name: '선택' }).click(); await page.getByLabel('관리자 비밀번호', { exact: true }).fill(password); await page.getByRole('button', { name: '구독 진행', exact: true }).click();
  await page.getByRole('button', { name: '테스트 결제 확인' }).click(); await page.getByLabel('관리자 비밀번호', { exact: true }).fill(password); await page.getByRole('button', { name: '실제 청구 없이 활성화' }).click(); await page.getByRole('heading', { name: 'team · active' }).waitFor();
  await page.screenshot({ path: 'saas-results/billing-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '사용자', exact: true }).click(); await page.getByRole('button', { name: '사용자 추가', exact: true }).click(); await page.locator('#form-dialog').getByLabel('이메일', { exact: true }).fill('analyst@example.test'); await page.locator('#form-dialog select[name="role"]').selectOption('analyst'); await page.getByRole('button', { name: '초대 메일 보내기' }).click(); await page.locator('#form-dialog').waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '연결 소스', exact: true }).click(); await page.getByRole('button', { name: '소스 추가', exact: true }).click(); await page.getByLabel('소스 이름').fill('판매용 샘플 앱'); await page.getByRole('button', { name: '소스 생성', exact: true }).click(); await page.getByRole('button', { name: '합성 인증 이벤트 6개 보내기' }).click(); await page.waitForFunction(() => document.querySelector('#metric-events').textContent === '6'); await page.locator('#form-dialog [aria-label="닫기"]').click();
  await page.getByRole('button', { name: /^탐지 사건/ }).click(); await page.getByText('반복 실패 후 인증 성공', { exact: true }).click(); await page.getByRole('button', { name: '처리 기한·티켓 지정' }).click();
  const due = new Date(Date.now() + 3600000); const local = new Date(due.getTime() - due.getTimezoneOffset() * 60000).toISOString().slice(0, 16); await page.getByLabel('처리 기한', { exact: true }).fill(local);
  await page.getByLabel('외부 티켓 번호·참조').fill('SEC-42'); await page.getByRole('button', { name: '기한 저장', exact: true }).click(); await page.locator('#form-dialog').waitFor({ state: 'hidden' }); await page.locator('#detail-dialog [aria-label="닫기"]').click();
  await page.getByRole('button', { name: '수집·처리 상태', exact: true }).click(); await page.getByText('SEC-42', { exact: true }).waitFor(); await page.screenshot({ path: 'saas-results/health-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '외부 연결', exact: true }).click(); await page.getByLabel('웹훅 토큰', { exact: true }).fill('browser-test-not-a-real-secret'); await page.getByLabel('관리자 비밀번호', { exact: true }).fill(password); await page.getByRole('button', { name: '연결 설정 저장' }).click(); await page.getByLabel('웹훅 토큰 (빈칸: 유지)', { exact: true }).waitFor(); assert.equal(await page.locator('input[name="webhook_token"]').inputValue(), '');
  await page.getByRole('button', { name: '데이터 관리', exact: true }).click(); await page.getByRole('button', { name: '데이터 내보내기', exact: true }).click(); await page.getByLabel('관리자 비밀번호', { exact: true }).fill(password); const download = page.waitForEvent('download'); await page.getByRole('button', { name: '조직 데이터 내보내기', exact: true }).click(); assert.equal((await download).suggestedFilename(), 'netsec-organization.json'); await page.locator('#form-dialog').waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '구독·사용량', exact: true }).click();
  for (const width of [390, 360]) { await page.setViewportSize({ width, height: 844 }); await page.screenshot({ path: `saas-results/billing-mobile-${width}.png`, fullPage: true }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true); }
  assert.deepEqual(errors, []); console.log('SaaS browser passed: signup, mail verification, login, trial, mock billing, invite, source, detection, deadline, health, encrypted integration, privacy export, mobile.');
} catch (error) { console.error(error); console.error(logs); process.exitCode = 1; }
finally { if (browser) await browser.close(); if (child.exitCode === null) { child.kill(); await new Promise(done => child.once('exit', done)); } await rm(temporary, { recursive: true, force: true }); }
