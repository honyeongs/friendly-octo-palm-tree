export const MAX_FILE_BYTES = 20 * 1024 * 1024;

const count = value => Number.isSafeInteger(value) && value >= 0;
const string = value => typeof value === 'string' && value.length <= 4096;
const timestamp = value => string(value) && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
function require(condition, message) { if (!condition) throw new Error(message); }
function eventValid(event) {
  return event && count(event.line_number) && event.line_number > 0 && timestamp(event.timestamp) && string(event.username) && string(event.method);
}

export function validateReport(report) {
  require(report && typeof report === 'object' && !Array.isArray(report), 'JSON 보고서 객체가 필요합니다.');
  require(['1.0', '1.1'].includes(report.schema_version), '지원하는 보고서 버전은 1.0, 1.1입니다.');
  require(string(report.source) && report.statistics && typeof report.statistics === 'object' && !Array.isArray(report.statistics), '보고서 출처 또는 통계가 없습니다.');
  require(Array.isArray(report.findings), '탐지 구간 형식이 올바르지 않습니다.');
  for (const [key, value] of Object.entries(report.statistics)) {
    if (key === 'malformed_line_numbers') require(Array.isArray(value) && value.every(count), '손상 로그 줄 번호가 올바르지 않습니다.');
    else require(count(value), '보고서 통계는 음수가 아닌 정수여야 합니다.');
  }
  for (const finding of report.findings) {
    require(finding && string(finding.host) && string(finding.source_ip) && Array.isArray(finding.usernames) && finding.usernames.every(string), '탐지 주소 또는 사용자 형식이 올바르지 않습니다.');
    require(timestamp(finding.start_time) && timestamp(finding.end_time) && Date.parse(finding.start_time) <= Date.parse(finding.end_time), '탐지 시각이 올바르지 않습니다.');
    require(count(finding.failure_count) && count(finding.peak_window_failures) && Array.isArray(finding.evidence) && finding.evidence.every(eventValid), '탐지 근거 형식이 올바르지 않습니다.');
    require(finding.evidence.length === finding.failure_count, '실패 횟수와 근거 수가 다릅니다.');
  }
  require(report.success_after_failures === undefined || Array.isArray(report.success_after_failures), '인증 상관분석 형식이 올바르지 않습니다.');
  for (const item of report.success_after_failures || []) {
    require(item && string(item.host) && string(item.source_ip) && string(item.username) && timestamp(item.success_time) && timestamp(item.start_time) && timestamp(item.end_time), '인증 상관분석 근거가 올바르지 않습니다.');
    require(count(item.failure_count) && count(item.success_line_number) && Array.isArray(item.failure_line_numbers) && item.failure_line_numbers.every(count), '인증 줄 번호가 올바르지 않습니다.');
    require(typeof item.seconds_after_last_failure === 'number' && Number.isFinite(item.seconds_after_last_failure) && item.seconds_after_last_failure >= 0, '인증 시간 차이가 올바르지 않습니다.');
  }
  if (report.network !== undefined) {
    const network = report.network;
    require(network && string(network.server_ip) && count(network.server_port) && Array.isArray(network.clients) && network.statistics, 'TCP 관측 형식이 올바르지 않습니다.');
    for (const value of Object.values(network.statistics)) require(count(value), '패킷 통계가 올바르지 않습니다.');
    for (const client of network.clients) {
      require(client && string(client.source_ip) && ['syn_packets', 'connection_attempts', 'syn_retransmissions', 'syn_ack_packets', 'reset_packets'].every(key => count(client[key])), 'TCP 클라이언트 통계가 올바르지 않습니다.');
      require(Array.isArray(client.evidence) && client.evidence.every(item => item && timestamp(item.timestamp) && count(item.packet_number) && ['syn', 'syn_ack', 'reset'].includes(item.kind) && string(item.client_ip)), '패킷 근거가 올바르지 않습니다.');
    }
    require(network.finding_links === undefined || Array.isArray(network.finding_links), '패킷 연결 근거가 올바르지 않습니다.');
    for (const link of network.finding_links || []) {
      require(link && count(link.finding_index) && count(link.connection_attempts) && Array.isArray(link.evidence), '패킷 연결 근거가 올바르지 않습니다.');
    }
  }
  return report;
}

export async function readReportFile(file) {
  if (file.size > MAX_FILE_BYTES) throw new Error('보고서는 20MB 이하 파일을 선택해 주세요.');
  let report;
  try { report = JSON.parse((await file.text()).replace(/^\uFEFF/, '')); }
  catch { throw new Error('JSON 파일을 읽을 수 없습니다.'); }
  return validateReport(report);
}

export function metrics(report) {
  return [report.statistics.failed_events || 0, report.findings.length,
    (report.success_after_failures || []).length, report.network?.statistics.connection_attempts || 0];
}

export function compareReports(a, b) {
  const grouped = new Map();
  for (const [side, report] of [['a', a], ['b', b]]) {
    for (const item of report.findings) {
      const key = JSON.stringify([item.host, item.source_ip]);
      if (!grouped.has(key)) grouped.set(key, {host: item.host, source_ip: item.source_ip, a: 0, b: 0, episodes_a: 0, episodes_b: 0});
      const row = grouped.get(key);
      row[side] += item.failure_count;
      row[`episodes_${side}`] += 1;
    }
  }
  return [...grouped.values()].map(row => ({...row, delta: row.b - row.a})).sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta) || x.source_ip.localeCompare(y.source_ip));
}

export function matches(value, query) {
  return !query.trim() || JSON.stringify(value).toLowerCase().includes(query.trim().toLowerCase());
}

export function formatTime(value, zone = 'UTC', withDate = false) {
  if (!value || !Number.isFinite(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat('en-GB', {timeZone: zone, hour12: false,
    ...(withDate ? {year: 'numeric', month: '2-digit', day: '2-digit'} : {}),
    hour: '2-digit', minute: '2-digit', second: '2-digit'}).format(new Date(value));
}
