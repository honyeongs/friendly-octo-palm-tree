import {readReportFile, validateReport} from './data.js';
import {renderOverview, renderWorkspace} from './render.js';

const state = {reports: {}, active: 'b', tab: 'findings', selected: 0, query: '', zone: 'UTC'};
const error = document.querySelector('#error');
let loadGeneration = 0;
const fileGeneration = {a: 0, b: 0};

function showError(message) { error.textContent = message; error.hidden = false; }
function clearError() { error.textContent = ''; error.hidden = true; }
function render() {
  if (!state.reports.a || !state.reports.b) return;
  renderOverview(state);
  renderWorkspace(state, index => { state.selected = index; render(); });
  document.querySelector('#export').disabled = false;
}

async function examples() {
  const generation = ++loadGeneration;
  clearError();
  document.querySelector('#reset').disabled = true;
  for (const input of document.querySelectorAll('input[type=file]')) input.disabled = true;
  try {
    const reports = await Promise.all(['baseline', 'extended'].map(async name => {
      const response = await fetch(`data/${name}.json`);
      if (!response.ok) throw new Error('예제 보고서를 불러올 수 없습니다.');
      return validateReport(await response.json());
    }));
    if (generation !== loadGeneration) return;
    [state.reports.a, state.reports.b] = reports;
    state.active = 'b'; state.selected = 0; state.query = ''; state.tab = 'findings';
    document.querySelector('#search').value = '';
    document.querySelector('#dataset-label').textContent = '합성 예제 데이터';
    render();
  } catch (problem) { showError(problem.message); }
  finally {
    document.querySelector('#reset').disabled = false;
    for (const input of document.querySelectorAll('input[type=file]')) input.disabled = false;
  }
}

async function loadFile(side, file) {
  if (!file) return;
  const generation = ++fileGeneration[side], examplesGeneration = loadGeneration;
  try {
    const report = await readReportFile(file);
    if (generation !== fileGeneration[side] || examplesGeneration !== loadGeneration) return;
    state.reports[side] = report; state.active = side; state.selected = 0;
    clearError();
    document.querySelector('#dataset-label').textContent = '로컬 보고서';
    render();
  } catch (problem) { showError(problem.message); }
}

for (const side of ['a', 'b']) {
  document.querySelector(`#active-${side}`).addEventListener('click', () => { state.active = side; state.selected = 0; render(); });
  document.querySelector(`#file-${side}`).addEventListener('change', event => {
    loadFile(side, event.target.files[0]); event.target.value = '';
  });
  const slot = document.querySelector(`#slot-${side}`);
  slot.addEventListener('dragover', event => { event.preventDefault(); slot.classList.add('dragging'); });
  slot.addEventListener('dragleave', () => slot.classList.remove('dragging'));
  slot.addEventListener('drop', event => {
    event.preventDefault(); slot.classList.remove('dragging'); loadFile(side, event.dataTransfer.files[0]);
  });
}
for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => { state.tab = button.dataset.tab; state.selected = 0; render(); });
document.querySelector('#search').addEventListener('input', event => { state.query = event.target.value; state.selected = 0; render(); });
document.querySelector('#timezone').addEventListener('change', event => { state.zone = event.target.value; render(); });
document.querySelector('#reset').addEventListener('click', examples);
document.querySelector('#export').disabled = true;
document.querySelector('#export').addEventListener('click', () => {
  const report = state.reports[state.active];
  if (!report) return;
  const blob = new Blob([JSON.stringify(report, null, 2) + '\n'], {type: 'application/json'});
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = `netsec-${state.active.toUpperCase()}.json`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
examples();
