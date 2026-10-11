import {compareReports, formatTime, matches, metrics} from './data.js';
import {badge, cells, el, empty, facts, table} from './dom.js';

const names = {findings: '탐지 구간', correlations: '인증 상관분석', network: 'TCP 관측', comparison: '보고서 비교'};
const deltaText = number => `${number > 0 ? '+' : ''}${number}`;

function evidenceList(items) {
  const list = el('ol', '', 'evidence-list');
  for (const item of items) {
    const row = el('li');
    row.append(el('span', '', `event-dot ${item.success ? 'success' : ''}`));
    const body = el('div', '', 'evidence-body');
    body.append(el('strong', item.title), el('small', item.meta));
    row.append(body); list.append(row);
  }
  return list;
}

export function renderOverview(state) {
  const {reports, active} = state;
  for (const side of ['a', 'b']) {
    const report = reports[side];
    document.querySelector(`#name-${side}`).textContent = report.source;
    document.querySelector(`#meta-${side}`).textContent = `${report.report_type === 'tcp' ? 'TCP' : 'SSH'} · v${report.schema_version} · ${report.statistics.parsed_events ?? report.statistics.total_packets ?? 0}건`;
    document.querySelector(`#active-${side}`).setAttribute('aria-pressed', String(active === side));
  }
  const values = metrics(reports[active]), a = metrics(reports.a), b = metrics(reports.b);
  const titles = ['인증 실패', '의심 구간', '실패 후 인증 성공', 'TCP 연결 시도'];
  const container = document.querySelector('#metrics');
  container.replaceChildren(...titles.map((title, index) => {
    const metric = el('div', '', 'metric');
    metric.append(el('div', title, 'metric-title'), el('div', values[index].toLocaleString('ko-KR'), 'metric-value'));
    const meta = el('div', '', 'metric-meta');
    meta.append(el('span', `A ${a[index]} · B ${b[index]}`));
    const difference = b[index] - a[index];
    meta.append(el('span', `B−A ${deltaText(difference)}`, `delta ${difference > 0 ? 'up' : difference < 0 ? 'down' : ''}`));
    metric.append(meta); return metric;
  }));
  const report = reports[active];
  document.querySelector('#count-findings').textContent = report.findings.length;
  document.querySelector('#count-correlations').textContent = (report.success_after_failures || []).length;
  document.querySelector('#count-network').textContent = report.network?.clients.length || 0;
  for (const button of document.querySelectorAll('[data-tab]')) {
    if (button.dataset.tab === state.tab) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
  const stats = report.statistics;
  document.querySelector('#source-info').textContent = `${report.source} · ${state.zone === 'UTC' ? 'UTC' : '한국 시간'} · 제외 ${stats.ignored_lines || 0}줄 · 손상 ${stats.malformed_lines || stats.malformed_packets || 0}건`;
  const note = document.querySelector('#parameter-note');
  const different = JSON.stringify(reports.a.parameters || {}) !== JSON.stringify(reports.b.parameters || {});
  note.hidden = !(state.tab === 'comparison' && different);
  note.textContent = 'A와 B의 분석 조건이 다릅니다. 횟수 차이를 해석할 때 시간 구간과 임계값을 함께 확인해 주세요.';
}

function rowsFor(state) {
  const report = state.reports[state.active];
  if (state.tab === 'findings') return report.findings.map((value, index) => ({value, index}));
  if (state.tab === 'correlations') return (report.success_after_failures || []).map((value, index) => ({value, index}));
  if (state.tab === 'network') return (report.network?.clients || []).map((value, index) => ({value, index}));
  return compareReports(state.reports.a, state.reports.b).map((value, index) => ({value, index}));
}

function address(item) {
  const node = el('div', item.source_ip);
  if (item.host) node.append(el('small', item.host));
  return node;
}

export function renderWorkspace(state, select) {
  const report = state.reports[state.active];
  const rows = rowsFor(state).filter(item => matches(item.value, state.query));
  const selected = rows.find(item => item.index === state.selected) || rows[0];
  const time = value => formatTime(value, state.zone);
  const result = document.querySelector('#results'), details = document.querySelector('#details');
  document.querySelector('#view-title').textContent = names[state.tab];
  document.querySelector('#result-count').textContent = `${rows.length}건`;
  document.querySelector('#detail-label').textContent = selected ? `${state.active.toUpperCase()} · ${selected.index + 1}` : '';
  if (!rows.length) {
    result.replaceChildren(empty(state.query ? '검색 결과가 없습니다.' : state.tab === 'network' ? '연결된 패킷 관측이 없습니다.' : '해당 항목이 없습니다.'));
    details.replaceChildren(empty('선택할 근거가 없습니다.'));
    return;
  }
  let headers;
  const domRows = rows.map(({value: item, index}) => {
    let values;
    if (state.tab === 'findings') {
      headers = ['출발지 / 호스트', '실패', '구간', '상태'];
      const correlated = (report.success_after_failures || []).some(value => value.host === item.host && value.source_ip === item.source_ip && value.failure_line_numbers.some(line => item.evidence.some(event => event.line_number === line)));
      values = [address(item), `${item.failure_count}회`, `${time(item.start_time)}–${time(item.end_time)}`, badge(correlated ? '이후 인증 성공' : '반복 실패', correlated ? 'success' : '')];
    } else if (state.tab === 'correlations') {
      headers = ['출발지 / 호스트', '사용자', '실패', '성공 시각'];
      values = [address(item), item.username, `${item.failure_count}회`, time(item.success_time)];
    } else if (state.tab === 'network') {
      headers = ['클라이언트', '연결 시도', 'SYN 재전송', 'RST'];
      values = [address(item), item.connection_attempts, item.syn_retransmissions, item.reset_packets];
    } else {
      headers = ['출발지 / 호스트', 'A 실패', 'B 실패', '차이 B−A'];
      values = [address(item), item.a, item.b, badge(deltaText(item.delta), item.delta < 0 ? 'success' : item.delta === 0 ? 'neutral' : '')];
    }
    const row = cells(values);
    row.firstChild.classList.add('address');
    row.className = `selectable ${selected.index === index ? 'selected' : ''}`;
    row.tabIndex = 0;
    row.setAttribute('aria-selected', String(selected.index === index));
    row.addEventListener('click', () => select(index));
    row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(index); } });
    return row;
  });
  result.replaceChildren(table(headers, domRows));
  const item = selected.value;
  const title = el('div', item.source_ip, 'detail-title');
  let factsNode, evidence = [], tail = [];
  if (state.tab === 'findings') {
    const link = report.network?.finding_links?.find(value => value.finding_index === selected.index);
    factsNode = facts([
      ['대상 호스트', item.host], ['대상 사용자', item.usernames.join(', ')],
      ['구간 시작', formatTime(item.start_time, state.zone, true)],
      ['구간 종료', formatTime(item.end_time, state.zone, true)],
      ['전체 실패', `${item.failure_count}회`], ['구간 최대', `${item.peak_window_failures}회`],
      ['분석 조건', `${report.parameters?.window_seconds ?? '?'}초 / ${report.parameters?.threshold ?? '?'}회`],
      ['패킷 연결', link ? `${link.connection_attempts}회 시도 · ${link.evidence.length}개 근거` : '연결 없음'],
    ]);
    evidence = item.evidence.map(event => ({title: `${time(event.timestamp)} · ${event.username}`, meta: `로그 ${event.line_number}줄 · ${event.method}${event.invalid_user ? ' · 미등록 사용자' : ''}`}));
  } else if (state.tab === 'correlations') {
    factsNode = facts([['대상 호스트', item.host], ['사용자', item.username], ['선행 실패', `${item.failure_count}회`], ['성공까지', `${item.seconds_after_last_failure}초`]]);
    evidence = [
      {title: `${time(item.start_time)}–${time(item.end_time)} · 인증 실패`, meta: `로그 ${item.failure_line_numbers.join(', ')}줄`},
      {title: `${time(item.success_time)} · 인증 성공`, meta: `로그 ${item.success_line_number}줄 · ${item.success_method}`, success: true},
    ];
    tail.push(el('p', '반복 실패 이후의 인증 성공입니다. 침해 여부는 별도 확인이 필요합니다.', 'transport-note'));
  } else if (state.tab === 'network') {
    factsNode = facts([['대상 서버', `${report.network.server_ip}:${report.network.server_port}`], ['연결 시도', item.connection_attempts], ['SYN-ACK', item.syn_ack_packets], ['SYN 재전송', item.syn_retransmissions], ['RST', item.reset_packets]]);
    evidence = item.evidence.map(event => ({title: `${time(event.timestamp)} · ${event.kind.toUpperCase()}`, meta: `패킷 #${event.packet_number} · 포트 ${event.client_port}`, success: event.kind === 'syn_ack'}));
    tail.push(el('p', 'TCP 관측 근거입니다. 응답 누락은 캡처 범위의 영향일 수 있으며, 암호화된 SSH 인증 내용은 포함하지 않습니다.', 'transport-note'));
  } else {
    factsNode = facts([['대상 호스트', item.host], ['A 의심 구간', `${item.episodes_a}개`], ['B 의심 구간', `${item.episodes_b}개`], ['실패 차이 B−A', deltaText(item.delta)]]);
    tail.push(el('p', `A: ${state.reports.a.source}`, 'transport-note'), el('p', `B: ${state.reports.b.source}`, 'transport-note'));
  }
  details.replaceChildren(title, factsNode);
  if (evidence.length) details.append(el('h3', `이벤트 근거 ${evidence.length}건`, 'subheading'), evidenceList(evidence));
  details.append(...tail);
}
