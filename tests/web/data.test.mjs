import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {compareReports, formatTime, matches, metrics, readReportFile, validateReport} from '../../src/netsec/web/data.js';

const extended = JSON.parse(readFileSync(new URL('../../src/netsec/web/data/extended.json', import.meta.url)));
const baseline = JSON.parse(readFileSync(new URL('../../src/netsec/web/data/baseline.json', import.meta.url)));
const original = JSON.parse(readFileSync(new URL('../../samples/ssh/demo-report.json', import.meta.url)));
const copy = value => JSON.parse(JSON.stringify(value));

test('accepts old and new report formats', () => {
  assert.equal(validateReport(original).schema_version, '1.0');
  assert.equal(validateReport(extended).schema_version, '1.1');
});
test('summary includes authentication and network counts', () => {
  assert.deepEqual(metrics(extended), [14, 2, 1, 6]);
});
test('comparison uses host and IP, with signed differences', () => {
  const rows = compareReports(baseline, extended);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].delta, 5);
  assert.equal(compareReports(extended, baseline)[0].delta, -5);
});
test('timestamp display includes correct UTC and Seoul offset', () => {
  assert.equal(formatTime('2026-10-11T00:01:00Z', 'UTC'), '00:01:00');
  assert.equal(formatTime('2026-10-11T00:01:00Z', 'Asia/Seoul'), '09:01:00');
});
test('search finds case-insensitive user, IP or host', () => {
  assert.ok(matches(extended.findings[0], 'ROOT'));
  assert.ok(matches(extended.findings[0], '192.0.2.10'));
  assert.ok(!matches(extended.findings[0], 'unmatched'));
});
test('rejects malformed report structure and non-finite values', () => {
  for (const mutate of [
    value => { value.schema_version = '99'; },
    value => { value.statistics.failed_events = -1; },
    value => { value.statistics = []; },
    value => { value.findings[0].evidence = []; },
    value => { value.findings[0].start_time = 'bad'; },
    value => { value.network.finding_links = {}; },
    value => { value.network.clients[0].connection_attempts = NaN; },
    value => { value.success_after_failures[0].failure_line_numbers = 'bad'; },
  ]) {
    const invalid = copy(extended); mutate(invalid);
    assert.throws(() => validateReport(invalid));
  }
});
test('file reader accepts UTF-8 BOM and validates contents', async () => {
  const file = {size: 100, text: async () => '\uFEFF' + JSON.stringify(extended)};
  assert.equal((await readReportFile(file)).findings.length, 2);
  await assert.rejects(() => readReportFile({size: 100, text: async () => '{'}));
});
test('file reader rejects large files before reading', async () => {
  await assert.rejects(() => readReportFile({size: 21 * 1024 * 1024, text: () => { throw new Error('should not read'); }}), /20MB/);
});
