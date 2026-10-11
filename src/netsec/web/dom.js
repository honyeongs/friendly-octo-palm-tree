export function el(tag, text = '', className = '') {
  const node = document.createElement(tag);
  if (text !== '') node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
export function badge(text, variant = '') { return el('span', text, `badge ${variant}`); }
export function empty(text) { return el('div', text, 'empty'); }
export function table(headers, rows) {
  const wrap = el('div', '', 'table-scroll');
  const node = el('table');
  const head = el('thead'), tr = el('tr');
  for (const title of headers) tr.append(el('th', title));
  head.append(tr);
  const body = el('tbody');
  body.append(...rows);
  node.append(head, body);
  wrap.append(node);
  return wrap;
}
export function cells(values) {
  const row = el('tr');
  for (const value of values) {
    const cell = el('td');
    cell.append(value instanceof Node ? value : document.createTextNode(String(value)));
    row.append(cell);
  }
  return row;
}
export function facts(items) {
  const node = el('dl', '', 'detail-grid');
  for (const [name, value] of items) node.append(el('dt', name), el('dd', value));
  return node;
}
