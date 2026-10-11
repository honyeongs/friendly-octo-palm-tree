import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const playwright = process.env.NETSEC_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(playwright.startsWith('.') || /^[A-Z]:/i.test(playwright) ? pathToFileURL(resolve(playwright)).href : playwright);
const python = process.env.NETSEC_PYTHON || 'python';
const temporary = await mkdtemp(join(tmpdir(), 'netsec-monitor-'));
await mkdir('monitor-results', { recursive: true });
async function port() { const server = createServer(); await new Promise(done => server.listen(0, '127.0.0.1', done)); const value = server.address().port; await new Promise(done => server.close(done)); return value; }
const mainPort = await port(); const demoPort = await port(); const base = `http://127.0.0.1:${mainPort}`; const sampleBase = `http://127.0.0.1:${demoPort}`;
const processes = []; let browser; let logs = '';
function start(args, env) { const child = spawn(python, ['run.py', ...args], { env: { ...process.env, ...env }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }); processes.push(child); child.stderr.on('data', data => { logs += data.toString(); }); return child; }
async function ready(url) { for (let i = 0; i < 100; i++) { try { if ((await fetch(url)).ok) return; } catch {} await new Promise(done => setTimeout(done, 150)); } throw new Error(`Server not ready: ${url}\n${logs}`); }
async function stop(child) { if (child.exitCode !== null) return; child.kill(); await Promise.race([new Promise(done => child.once('exit', done)), new Promise(done => setTimeout(done, 5000))]); }

try {
  let monitor = start(['monitor', '--port', String(mainPort)], { NETSEC_ORIGIN: base, NETSEC_DB: join(temporary, 'main.sqlite3') }); await ready(`${base}/healthz`);
  browser = await chromium.launch({ headless: true }); const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }); const page = await context.newPage(); const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base); await page.getByRole('heading', { name: '첫 조직 설정' }).waitFor();
  await page.getByLabel('조직 이름').fill('NetSec QA'); await page.getByLabel('관리자 이름').fill('QA 관리자'); await page.getByLabel('이메일', { exact: true }).fill('qa@example.test'); await page.getByLabel('비밀번호', { exact: true }).fill('Browser test password 123!'); await page.getByRole('button', { name: '조직·관리자 생성' }).click();
  await page.locator('#workspace').waitFor({ state: 'visible' }); await page.getByText('탐지된 사건이 없습니다').waitFor();
  await page.getByRole('button', { name: '연결 소스', exact: true }).click(); await page.getByRole('button', { name: '소스 추가', exact: true }).click(); await page.getByLabel('소스 이름').fill('샘플 쇼핑몰'); await page.getByRole('button', { name: '소스 생성', exact: true }).click();
  await page.locator('#source-token').waitFor(); const key = await page.locator('#source-token').textContent(); assert.match(key, /^nsk_/);
  await page.getByRole('button', { name: '합성 인증 이벤트 6개 보내기' }).click(); await page.waitForFunction(() => document.querySelector('#metric-events').textContent === '6');
  await page.locator('#form-dialog [aria-label="닫기"]').click(); await page.getByRole('button', { name: /^탐지 사건/ }).click(); await page.getByText('반복 실패 후 인증 성공', { exact: true }).waitFor();
  await page.screenshot({ path: 'monitor-results/desktop.png', fullPage: true });
  await page.getByText('반복 실패 후 인증 성공', { exact: true }).click(); await page.getByLabel('처리 상태').selectOption('investigating'); await page.getByLabel('담당자').selectOption({ label: 'QA 관리자' }); await page.getByRole('button', { name: '변경 저장', exact: true }).click(); await page.waitForFunction(() => document.querySelector('#detail-dialog select[name="status"]').value === 'investigating');
  await page.getByRole('textbox', { name: '조사 메모', exact: true }).fill('<img src=x onerror=alert(1)> 검토 완료'); await page.getByRole('button', { name: '메모 등록' }).click(); await page.getByText('<img src=x onerror=alert(1)> 검토 완료', { exact: true }).waitFor(); assert.equal(await page.locator('#detail-content img').count(), 0);
  await page.screenshot({ path: 'monitor-results/incident.png', fullPage: true }); await page.locator('#detail-dialog [aria-label="닫기"]').click();
  const downloaded = page.waitForEvent('download'); await page.getByRole('button', { name: '사건 JSON 내보내기' }).click(); assert.equal((await downloaded).suggestedFilename(), 'netsec-incidents.json');
  await page.getByRole('button', { name: '인증 기록', exact: true }).click(); await page.locator('#search').fill('192.0.2.25'); await page.getByRole('button', { name: '검색', exact: true }).click(); await page.waitForFunction(() => document.querySelectorAll('#content tbody tr').length === 6);

  start(['demo-app', '--port', String(demoPort), '--endpoint', base], { NETSEC_SOURCE_KEY: key, NETSEC_DEMO_DB: join(temporary, 'demo.sqlite3'), NETSEC_DEMO_OUTBOX: join(temporary, 'outbox.sqlite3') }); await ready(`${sampleBase}/api/state`);
  const sample = await context.newPage(); await sample.goto(sampleBase); await sample.getByLabel('아이디').fill('shop-user'); await sample.getByLabel('비밀번호').fill('Sample app password 123!'); await sample.getByRole('button', { name: '계정 생성', exact: true }).click(); await sample.getByRole('heading', { name: '샘플 앱 로그인' }).waitFor();
  for (let index = 0; index < 5; index++) { await sample.getByLabel('비밀번호').fill('incorrect password'); await sample.getByRole('button', { name: '로그인', exact: true }).click(); await sample.getByText('아이디 또는 비밀번호가 일치하지 않습니다.', { exact: true }).waitFor(); await sample.locator('#submit:not([disabled])').waitFor(); }
  await sample.getByLabel('비밀번호').fill('Sample app password 123!'); await sample.getByRole('button', { name: '로그인', exact: true }).click(); await sample.getByText('shop-user님, 인증되었습니다.').waitFor();
  await new Promise(done => setTimeout(done, 3000)); await page.getByRole('button', { name: /^탐지 사건/ }).click(); await page.locator('#search').fill(''); await page.getByRole('button', { name: '검색', exact: true }).click(); await page.waitForFunction(() => document.querySelector('#metric-events').textContent === '12');
  await stop(monitor); monitor = start(['monitor', '--port', String(mainPort)], { NETSEC_ORIGIN: base, NETSEC_DB: join(temporary, 'main.sqlite3') }); await ready(`${base}/healthz`);
  await page.reload(); await page.waitForFunction(() => document.querySelector('#metric-events').textContent === '12'); assert.equal(await page.locator('#content tbody tr').count(), 4);
  for (const width of [390, 360]) { await page.setViewportSize({ width, height: 844 }); await page.screenshot({ path: `monitor-results/mobile-${width}.png`, fullPage: true }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true); }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '사용자', exact: true }).click(); await page.getByRole('button', { name: '사용자 추가', exact: true }).click(); await page.getByLabel('이름', { exact: true }).fill('조회 담당자'); await page.locator('#form-dialog').getByLabel('이메일', { exact: true }).fill('viewer@example.test'); await page.getByLabel('초기 비밀번호').fill('Viewer test password 123!'); await page.locator('#form-dialog button[type="submit"]').click(); await page.locator('#form-dialog').waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '로그아웃', exact: true }).click(); await page.getByLabel('이메일', { exact: true }).fill('viewer@example.test'); await page.getByLabel('비밀번호', { exact: true }).fill('Viewer test password 123!'); await page.getByRole('button', { name: '로그인', exact: true }).click(); await page.locator('#workspace').waitFor({ state: 'visible' });
  assert.equal(await page.getByRole('button', { name: '사용자', exact: true }).isVisible(), false); await page.getByRole('button', { name: '연결 소스', exact: true }).click(); assert.equal(await page.getByRole('button', { name: '소스 추가', exact: true }).isVisible(), false);
  await page.getByRole('button', { name: /^탐지 사건/ }).click(); await page.locator('#content tr.clickable').first().click(); await page.locator('#detail-dialog').waitFor({ state: 'visible' }); assert.equal(await page.getByRole('button', { name: '변경 저장', exact: true }).count(), 0);
  assert.deepEqual(errors, []); console.log('Monitor browser: setup, source, ingestion, investigation, export, sample app, restart, mobile, viewer passed.');
} catch (error) { console.error(error); if (logs) console.error(logs); process.exitCode = 1; }
finally { if (browser) await browser.close(); for (const child of processes.reverse()) await stop(child); await rm(temporary, { recursive: true, force: true }); }
