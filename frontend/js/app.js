'use strict';

// ── Device icons (Lucide-style inline SVG paths) ──────────────
const ICONS = {
  firewall: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    <path d="M9.5 9a2.5 2.5 0 0 1 5 0v.5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2V9z"/>
  </svg>`,
  cisco_switch: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="4" width="20" height="6" rx="1"/>
    <rect x="2" y="14" width="20" height="6" rx="1"/>
    <circle cx="6" cy="7" r="1" fill="currentColor"/>
    <circle cx="6" cy="17" r="1" fill="currentColor"/>
    <line x1="10" y1="7" x2="18" y2="7"/>
    <line x1="10" y1="17" x2="18" y2="17"/>
  </svg>`,
  ruckus_switch: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="6" width="20" height="12" rx="2"/>
    <line x1="6" y1="10" x2="6" y2="14"/>
    <line x1="9" y1="10" x2="9" y2="14"/>
    <line x1="12" y1="10" x2="12" y2="14"/>
    <line x1="15" y1="10" x2="15" y2="14"/>
    <line x1="18" y1="10" x2="18" y2="14"/>
  </svg>`,
  ruckus_ap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
    <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
    <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
    <circle cx="12" cy="20" r="1" fill="currentColor"/>
  </svg>`,
  wireless_client: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9"/>
    <path d="M4 16h16l1.28 2.55A1 1 0 0 1 20.38 20H3.62a1 1 0 0 1-.9-1.45L4 16z"/>
    <path d="M9.5 9.5a3.5 3.5 0 0 1 5 0"/>
    <circle cx="12" cy="13" r="1" fill="currentColor"/>
  </svg>`,
  wired_client: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2"/>
    <line x1="8" y1="21" x2="16" y2="21"/>
    <line x1="12" y1="17" x2="12" y2="21"/>
  </svg>`,
  aruba_switch: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="5" width="20" height="7" rx="1"/>
    <rect x="2" y="14" width="20" height="5" rx="1"/>
    <circle cx="6" cy="8.5" r="1" fill="currentColor"/>
    <circle cx="9" cy="8.5" r="1" fill="currentColor"/>
    <line x1="13" y1="8.5" x2="18" y2="8.5"/>
  </svg>`,
  aruba_ap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
    <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
    <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
    <circle cx="12" cy="20" r="1" fill="currentColor"/>
    <line x1="12" y1="3" x2="12" y2="7"/>
  </svg>`,
  extreme_switch: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="6" width="20" height="12" rx="2"/>
    <path d="M7 10l2 2-2 2"/>
    <line x1="12" y1="10" x2="17" y2="10"/>
    <line x1="12" y1="14" x2="17" y2="14"/>
  </svg>`,
  extreme_ap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
    <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
    <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
    <circle cx="12" cy="20" r="1" fill="currentColor"/>
    <path d="M10 4l2-2 2 2"/>
  </svg>`,
  unknown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
    <line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>`,
};

// ── Constants ─────────────────────────────────────────────────
const DEVICE_META = {
  firewall:         { icon: ICONS.firewall,        label: 'Firewall',        cls: 'fw'       },
  cisco_switch:     { icon: ICONS.cisco_switch,    label: 'Cisco Switch',    cls: 'cisco_sw' },
  ruckus_switch:    { icon: ICONS.ruckus_switch,   label: 'Ruckus Switch',   cls: 'r1_sw'    },
  ruckus_ap:        { icon: ICONS.ruckus_ap,       label: 'Access Point',    cls: 'ap'       },
  aruba_switch:     { icon: ICONS.aruba_switch,    label: 'Aruba Switch',    cls: 'aruba_sw' },
  aruba_ap:         { icon: ICONS.aruba_ap,        label: 'Aruba AP',        cls: 'ap'       },
  extreme_switch:   { icon: ICONS.extreme_switch,  label: 'Extreme Switch',  cls: 'ext_sw'   },
  extreme_ap:       { icon: ICONS.extreme_ap,      label: 'Extreme AP',      cls: 'ap'       },
  wireless_client:  { icon: ICONS.wireless_client, label: 'WiFi Client',     cls: 'client'   },
  wired_client:     { icon: ICONS.wired_client,    label: 'Wired Device',    cls: 'client'   },
  unknown:          { icon: ICONS.unknown,         label: 'Unknown',         cls: 'unknown'  },
};

// ── API key ───────────────────────────────────────────────────
let _apiKey = sessionStorage.getItem('netinspect_api_key') || '';

function apiHeaders(extra = {}) {
  const h = { ...extra };
  if (_apiKey) h['X-API-Key'] = _apiKey;
  return h;
}

async function apiFetch(url, opts = {}) {
  opts.headers = apiHeaders(opts.headers || {});
  const res = await fetch(url, opts);
  if (res.status === 403) {
    const key = prompt('API key required:');
    if (!key) throw new Error('API key required');
    _apiKey = key;
    sessionStorage.setItem('netinspect_api_key', key);
    opts.headers['X-API-Key'] = key;
    return fetch(url, opts);
  }
  return res;
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initUI();
  _syncThemeButton();   // set label/icon to match saved theme
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') doTrace();
  });
});

async function initUI() {
  let caps = {};
  try {
    const res = await fetch('/api/capabilities');
    if (res.ok) caps = await res.json();
  } catch (_) { /* server unreachable — show nothing */ }
  renderVendorBar(caps);
  updateSearchHints(caps);
}

function renderVendorBar(caps = {}) {
  const vendors = [];
  // On-prem — only show vendors that are actually configured
  if (caps.fortigate)                              vendors.push({ label: 'Fortinet',      group: 'onprem' });
  if (caps.cisco_switches)                         vendors.push({ label: 'Cisco IOS',     group: 'onprem' });
  if (caps.aruba_switches)                         vendors.push({ label: 'Aruba',         group: 'onprem' });
  if (caps.ruckus_r1)                              vendors.push({ label: 'Ruckus ICX',    group: 'onprem' });
  // Cloud
  if (caps.ruckus_r1)                              vendors.push({ label: 'Ruckus One',    group: 'cloud'  });
  if (caps.aruba_central)                          vendors.push({ label: 'Aruba Central', group: 'cloud'  });
  if (caps.extreme_iq)                             vendors.push({ label: 'XIQ',           group: 'cloud'  });

  const el = document.getElementById('deviceSummary');
  if (!vendors.length) {
    el.innerHTML = '<span class="badge badge-neutral">No integrations configured</span>';
    return;
  }
  el.innerHTML = vendors.map(v =>
    `<span class="vendor-chip vendor-chip--${esc(v.group)}">${esc(v.label)}</span>`
  ).join('');
}

function updateSearchHints(caps = {}) {
  const parts = ['MAC address', 'IP address'];
  if (caps.fortigate) parts.push('FortiGate address name');
  document.getElementById('searchInput').placeholder = parts.join('  ·  ');

  // Add FortiGate address name example only when FG is configured
  const exRow = document.querySelector('.search-examples');
  if (exRow && caps.fortigate && !exRow.querySelector('[data-fg-example]')) {
    const code = document.createElement('code');
    code.setAttribute('onclick', 'fillExample(this)');
    code.setAttribute('data-fg-example', '1');
    code.textContent = 'Server-Web-01';
    exRow.appendChild(code);
  }
}

function mkBadge(text, type) {
  const b = document.createElement('span');
  b.className = `badge badge-${type}`;
  b.textContent = text;
  return b;
}

// ── Options panel ─────────────────────────────────────────────
function toggleOptions() {
  const panel = document.getElementById('optionsPanel');
  const caret = document.getElementById('optionsCaret');
  const open  = panel.classList.toggle('open');
  caret.style.transform = open ? 'rotate(90deg)' : '';
}

function updateOptionsLabel() {
  const keys = ['interface_status', 'error_counters', 'mtu_check', 'stp', 'poe', 'neighbor_info', 'system_logs'];
  const enabled = keys.filter(k => document.getElementById('opt_' + k)?.checked).length;
  const label = document.getElementById('optionsToggleLabel');
  label.textContent = enabled === keys.length
    ? 'Diagnostics: All enabled'
    : `Diagnostics: ${enabled} / ${keys.length} enabled`;
}

function getOptions() {
  return {
    interface_status: !!document.getElementById('opt_interface_status')?.checked,
    error_counters:   !!document.getElementById('opt_error_counters')?.checked,
    mtu_check:        !!document.getElementById('opt_mtu_check')?.checked,
    stp:              !!document.getElementById('opt_stp')?.checked,
    poe:              !!document.getElementById('opt_poe')?.checked,
    neighbor_info:    !!document.getElementById('opt_neighbor_info')?.checked,
    system_logs:      !!document.getElementById('opt_system_logs')?.checked,
    wireless_info:    true,
  };
}

function toggleTheme() {
  const html  = document.documentElement;
  const isLight = html.getAttribute('data-theme') === 'light';
  if (isLight) {
    html.removeAttribute('data-theme');
  } else {
    html.setAttribute('data-theme', 'light');
  }
  localStorage.setItem('netinspect_theme', isLight ? 'dark' : 'light');
  _syncThemeButton();
}

function _syncThemeButton() {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const label = document.getElementById('themeLabel');
  if (label) label.textContent = isLight ? 'Dark' : 'Light';
  // icon visibility is handled by CSS [data-theme="light"] rules
}

// ── Trace ─────────────────────────────────────────────────────
async function doTrace() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;

  setState('loading');

  try {
    const res = await apiFetch('/api/trace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, options: getOptions() }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Server error');
    }
    const data = await res.json();
    renderResults(data);
    setState('results');
  } catch (e) {
    showError(e.message);
  }
}

function fillExample(el) {
  document.getElementById('searchInput').value = el.textContent;
  document.getElementById('searchInput').focus();
}

// ── State management ──────────────────────────────────────────
function setState(state) {
  ['loadingState', 'errorState', 'resultsSection'].forEach(id =>
    document.getElementById(id).classList.add('hidden')
  );
  document.getElementById('traceBtn').disabled = state === 'loading';
  if (state === 'loading')  document.getElementById('loadingState').classList.remove('hidden');
  if (state === 'results')  document.getElementById('resultsSection').classList.remove('hidden');
}

function showError(msg) {
  document.getElementById('errorMessage').textContent = msg;
  document.getElementById('errorState').classList.remove('hidden');
  document.getElementById('loadingState').classList.add('hidden');
  document.getElementById('traceBtn').disabled = false;
}

// ── Render results ────────────────────────────────────────────
function renderResults(data) {
  renderSummaryBar(data);
  renderPath(data.path || []);
  renderIssues(data.all_issues || []);
  renderTestsSummary(data.test_summary || []);
  renderHopDetails(data.path || []);
}

function renderSummaryBar(data) {
  const hasCrit = (data.all_issues || []).some(i => i.severity === 'critical');
  const hasWarn = (data.all_issues || []).some(i => i.severity === 'warning');
  const iconEl  = document.getElementById('summaryIcon');
  const titleEl = document.getElementById('summaryTitle');
  const metaEl  = document.getElementById('summaryMeta');
  const badgesEl = document.getElementById('summaryBadges');

  if (data.status === 'not_found') {
    iconEl.textContent  = '🔍';
    titleEl.textContent = 'Device not found';
    titleEl.style.color = 'var(--warn)';
  } else if (hasCrit) {
    iconEl.textContent  = '🔴';
    titleEl.textContent = 'Issues detected';
    titleEl.style.color = 'var(--crit)';
  } else if (hasWarn) {
    iconEl.textContent  = '⚠️';
    titleEl.textContent = 'Warnings found';
    titleEl.style.color = 'var(--warn)';
  } else {
    iconEl.textContent  = '✅';
    titleEl.textContent = 'Trace complete';
    titleEl.style.color = 'var(--ok)';
  }

  const parts = [];
  if (data.resolved_mac) parts.push(`MAC: ${data.resolved_mac}`);
  if (data.resolved_ip)  parts.push(`IP: ${data.resolved_ip}`);
  if (data.trace_time_ms) parts.push(`${data.trace_time_ms}ms`);
  metaEl.textContent = parts.join('  ·  ');

  badgesEl.innerHTML = '';
  const crits = (data.all_issues || []).filter(i => i.severity === 'critical').length;
  const warns = (data.all_issues || []).filter(i => i.severity === 'warning').length;
  const passes = (data.test_summary || []).filter(t => t.status === 'pass').length;
  if (crits) badgesEl.appendChild(mkBadge(`🔴 ${crits} Critical`, 'crit'));
  if (warns) badgesEl.appendChild(mkBadge(`⚠️ ${warns} Warning`, 'warn'));
  if (!crits && !warns) badgesEl.appendChild(mkBadge('✓ All clear', 'ok'));
  if (data.path) badgesEl.appendChild(mkBadge(`${data.path.length} hops`, 'neutral'));
  if (passes) badgesEl.appendChild(mkBadge(`${passes} tests passed`, 'ok'));
}

function renderPath(path) {
  const container = document.getElementById('pathContainer');
  if (!path.length) { container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px">No path data</div>'; return; }

  const flow = document.createElement('div');
  flow.className = 'path-flow';

  path.forEach((hop, idx) => {
    const meta = DEVICE_META[hop.device_type] || DEVICE_META.unknown;
    const hasCrit = hop.issues.some(i => i.severity === 'critical');
    const hasWarn = hop.issues.some(i => i.severity === 'warning');

    const node = document.createElement('div');
    node.className = 'path-node';
    node.title = hop.device_name;
    node.onclick = () => scrollToHop(idx);

    const iconWrap = document.createElement('div');
    iconWrap.className = `node-icon ${meta.cls}`;
    iconWrap.innerHTML = meta.icon;

    if (hasCrit || hasWarn) {
      const dot = document.createElement('span');
      dot.className = `issue-dot ${hasCrit ? 'crit' : 'warn'}`;
      iconWrap.appendChild(dot);
    }

    const label = document.createElement('div');
    label.className = 'node-label';
    label.textContent = hop.device_name;

    const sub = document.createElement('div');
    sub.className = 'node-sub';
    // Show vendor+model if available, else IP, else device type label
    const vendorModel = [hop.vendor, hop.model].filter(Boolean).join(' ');
    sub.textContent = vendorModel || hop.device_ip || meta.label;

    const portInfo = document.createElement('div');
    portInfo.className = 'node-port';
    const portText = [hop.ingress_port, hop.egress_port].filter(Boolean).join(' → ');
    portInfo.textContent = portText;

    // Fixed-height icon row — keeps all icons at the same vertical position
    const nodeIconRow = document.createElement('div');
    nodeIconRow.className = 'node-icon-row';
    nodeIconRow.appendChild(iconWrap);

    // Variable-height info row — text sits below, doesn't affect icon alignment
    const nodeInfo = document.createElement('div');
    nodeInfo.className = 'node-info';
    nodeInfo.appendChild(label);
    nodeInfo.appendChild(sub);
    nodeInfo.appendChild(portInfo);  // always append even if empty

    node.appendChild(nodeIconRow);
    node.appendChild(nodeInfo);
    flow.appendChild(node);

    if (idx < path.length - 1) {
      const arrow = document.createElement('div');
      arrow.className = 'path-arrow';

      // Fixed-height arrow icon row — same height as node-icon-row so line aligns with icons
      const arrowIconRow = document.createElement('div');
      arrowIconRow.className = 'arrow-icon-row';

      const nextHop = path[idx + 1];
      const connLabel = buildConnLabel(hop, nextHop);
      if (connLabel) {
        const lbl = document.createElement('div');
        lbl.className = 'arrow-conn-label';
        lbl.textContent = connLabel;
        arrowIconRow.appendChild(lbl);
      }
      const line = document.createElement('div');
      line.className = 'arrow-line';
      arrowIconRow.appendChild(line);
      arrow.appendChild(arrowIconRow);
      flow.appendChild(arrow);
    }
  });

  container.innerHTML = '';
  container.appendChild(flow);
}

function buildConnLabel(hop, nextHop) {
  // Show "egress→ingress" ports between two hops
  const from = hop.egress_port;
  const to   = nextHop.ingress_port;
  if (from && to) return `${from} → ${to}`;
  if (from) return from;
  if (to)   return to;
  return '';
}

function renderIssues(issues) {
  const section = document.getElementById('issuesSection');
  const list    = document.getElementById('issuesList');
  if (!issues.length) { section.classList.add('hidden'); return; }
  section.classList.remove('hidden');
  list.innerHTML = '';
  issues.forEach(issue => {
    const item = document.createElement('div');
    item.className = `issue-item ${issue.severity}`;
    item.innerHTML = `
      <span class="issue-sev ${issue.severity}">${issue.severity}</span>
      <div class="issue-body">
        ${issue.device ? `<div class="issue-device">${esc(issue.device)}</div>` : ''}
        <div class="issue-msg">${esc(issue.message)}</div>
        ${issue.detail ? `<div class="issue-detail">${esc(issue.detail)}</div>` : ''}
      </div>`;
    list.appendChild(item);
  });
}

function renderTestsSummary(tests) {
  const section = document.getElementById('testsSection');
  const container = document.getElementById('testsSummary');
  if (!tests.length) { section.classList.add('hidden'); return; }
  section.classList.remove('hidden');

  const counts = { pass: 0, fail: 0, warning: 0, skip: 0, na: 0 };
  tests.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++; });

  const statsBar = document.createElement('div');
  statsBar.className = 'tests-stats';
  if (counts.pass)    statsBar.appendChild(mkBadge(`✓ ${counts.pass} passed`, 'ok'));
  if (counts.fail)    statsBar.appendChild(mkBadge(`✗ ${counts.fail} failed`, 'crit'));
  if (counts.warning) statsBar.appendChild(mkBadge(`⚠ ${counts.warning} warnings`, 'warn'));
  if (counts.skip)    statsBar.appendChild(mkBadge(`– ${counts.skip} skipped`, 'neutral'));

  const grid = document.createElement('div');
  grid.className = 'tests-grid';

  tests.forEach(test => {
    if (test.status === 'skip' || test.status === 'na') return;
    const item = document.createElement('div');
    item.className = `test-item test-${test.status}`;
    const icon = { pass: '✓', fail: '✗', warning: '⚠', skip: '–', na: '–' }[test.status] || '–';
    item.innerHTML = `
      <span class="test-icon test-icon-${test.status}">${icon}</span>
      <div class="test-body">
        <div class="test-name">${esc(test.name)}</div>
        ${test.value ? `<div class="test-value">${esc(test.value)}</div>` : ''}
        ${test.message ? `<div class="test-msg">${esc(test.message)}</div>` : ''}
      </div>`;
    grid.appendChild(item);
  });

  container.innerHTML = '';
  container.appendChild(statsBar);
  if (grid.children.length) container.appendChild(grid);
}

function renderHopDetails(path) {
  const container = document.getElementById('hopDetails');
  container.innerHTML = '';
  path.forEach((hop, idx) => {
    container.appendChild(buildHopCard(hop, idx));
  });
}

function buildHopCard(hop, idx) {
  const meta     = DEVICE_META[hop.device_type] || DEVICE_META.unknown;
  const hasCrit  = hop.issues.some(i => i.severity === 'critical');
  const hasWarn  = hop.issues.some(i => i.severity === 'warning');

  const card = document.createElement('div');
  card.className = 'hop-card';
  card.id = `hop-${idx}`;

  // Header
  const header = document.createElement('div');
  header.className = 'hop-header';
  header.onclick = () => card.classList.toggle('open');

  const hopIcon = document.createElement('div');
  hopIcon.className = `hop-icon ${meta.cls}`;
  hopIcon.innerHTML = meta.icon;
  hopIcon.style.borderColor = getDeviceColor(hop.device_type);
  hopIcon.style.background  = getDeviceColor(hop.device_type, 0.1);
  hopIcon.style.color       = getDeviceColor(hop.device_type);

  const titleGroup = document.createElement('div');
  titleGroup.className = 'hop-title-group';
  const vendorModel = [hop.vendor, hop.model].filter(Boolean).join(' ');
  const subLine = [
    hop.device_ip || meta.label,
    vendorModel,
    hop.ingress_port ? `in: ${hop.ingress_port}` : '',
  ].filter(Boolean).join(' · ');
  titleGroup.innerHTML = `
    <div class="hop-title">${esc(hop.device_name)}</div>
    <div class="hop-subtitle">${esc(subLine)}</div>`;

  const badges = document.createElement('div');
  badges.className = 'hop-badges';
  if (!hop.reachable && hop.device_type === 'cisco_switch') badges.appendChild(mkBadge('Unreachable', 'crit'));
  if (hop.vlan) badges.appendChild(mkBadge('VLAN ' + hop.vlan, 'info'));
  if (hop.software_version) badges.appendChild(mkBadge(hop.software_version, 'neutral'));
  if (hasCrit)  badges.appendChild(mkBadge('⚠ Issues', 'crit'));
  else if (hasWarn) badges.appendChild(mkBadge('⚠ Warning', 'warn'));
  else if (hop.reachable || hop.device_type !== 'cisco_switch') badges.appendChild(mkBadge('OK', 'ok'));

  const chevron = document.createElement('span');
  chevron.className = 'hop-chevron';
  chevron.textContent = '›';

  header.appendChild(hopIcon);
  header.appendChild(titleGroup);
  header.appendChild(badges);
  header.appendChild(chevron);

  // Body
  const body = document.createElement('div');
  body.className = 'hop-body';

  // Device info (vendor/model/version row)
  if (hop.vendor || hop.model || hop.software_version) {
    body.innerHTML += `<div class="subsection-title">Device Info</div>`;
    body.appendChild(buildDetailGrid([
      ['Vendor',  hop.vendor  || '–'],
      ['Model',   hop.model   || '–'],
      ['Version', hop.software_version || '–'],
      ['IP',      hop.device_ip || '–'],
    ]));
  }

  // Port connections
  if (hop.ingress_port || hop.egress_port) {
    body.innerHTML += `<div class="subsection-title">Port Connections</div>`;
    body.appendChild(buildDetailGrid([
      ['Ingress Port', hop.ingress_port || '–'],
      ['Egress Port',  hop.egress_port  || '–'],
    ]));
  }

  // Interface status
  if (hop.interface_status) {
    body.innerHTML += `<div class="subsection-title">Interface Status</div>`;
    body.appendChild(buildDetailGrid([
      ['Port',   hop.interface_status.name],
      ['Status', hop.interface_status.status, statusColor(hop.interface_status.status)],
      ['VLAN',   hop.interface_status.vlan],
      ['Duplex', hop.interface_status.duplex, hop.interface_status.duplex?.includes('half') ? 'warn' : 'ok'],
      ['Speed',  hop.interface_status.speed],
      ['Type',   hop.interface_status.port_type],
    ]));
  }

  // Interface details
  if (hop.interface_details) {
    const d = hop.interface_details;
    body.innerHTML += `<div class="subsection-title">Interface Details</div>`;
    body.appendChild(buildDetailGrid([
      ['MTU',            fmtMtu(d.mtu, hop.raw_data), d.mtu && d.mtu !== 1500 ? 'warn' : ''],
      ['Input Errors',   d.input_errors,  d.input_errors > 0   ? 'warn' : 'ok'],
      ['Output Errors',  d.output_errors, d.output_errors > 0  ? 'warn' : 'ok'],
      ['CRC Errors',     d.crc_errors,    d.crc_errors > 0     ? 'crit' : 'ok'],
      ['Runts',          d.runts,         d.runts > 0          ? 'warn' : 'ok'],
      ['Giants',         d.giants,        d.giants > 0         ? 'warn' : 'ok'],
      ['Input Rate',     d.input_rate_bps  ? fmtBps(d.input_rate_bps)  : '–'],
      ['Output Rate',    d.output_rate_bps ? fmtBps(d.output_rate_bps) : '–'],
      ['Description',    d.description || '–'],
    ]));
  }

  // CDP / LLDP neighbor
  const neighbor = hop.cdp_neighbor || hop.lldp_neighbor;
  if (neighbor) {
    const proto = hop.cdp_neighbor ? 'CDP' : 'LLDP';
    body.innerHTML += `<div class="subsection-title">Neighbor (${proto})</div>`;
    body.appendChild(buildDetailGrid([
      ['Device',      neighbor.remote_device],
      ['Remote Port', neighbor.remote_port],
      ['Remote IP',   neighbor.remote_ip || '–'],
      ['Platform',    neighbor.platform || neighbor.system_description || '–'],
    ]));
  }

  // STP
  if (hop.stp_info && hop.stp_info.length) {
    body.innerHTML += `<div class="subsection-title">Spanning Tree</div>`;
    const rows = hop.stp_info.map(s => [
      `VLAN ${s.vlan}`, `${s.role.toUpperCase()} · ${s.state.toUpperCase()} · cost ${s.cost}`,
      s.state.toLowerCase().includes('blk') ? 'warn' : 'ok'
    ]);
    body.appendChild(buildDetailGrid(rows));
  }

  // PoE
  if (hop.poe_status) {
    const p = hop.poe_status;
    body.innerHTML += `<div class="subsection-title">PoE</div>`;
    body.appendChild(buildDetailGrid([
      ['Admin',    p.admin],
      ['Status',   p.operational, p.operational.toLowerCase().includes('deny') ? 'crit' : 'ok'],
      ['Power',    p.power_watts ? p.power_watts + ' W' : '–'],
      ['Max',      p.max_watts   ? p.max_watts   + ' W' : '–'],
      ['Class',    p.poe_class || '–'],
      ['Device',   p.device || '–'],
    ]));
  }

  // Ruckus ICX switch — ingress port info from R1 API (speed / duplex / status)
  if (hop.device_type === 'ruckus_switch' && hop.raw_data && hop.raw_data.r1_port_data) {
    const p = hop.raw_data.r1_port_data;
    // R1 uses various field names across firmware versions — try all known variants
    const speed  = p.speed  ?? p.portSpeed  ?? p._raw?.speed  ?? p._raw?.portSpeed  ?? p._raw?.linkSpeed;
    const duplex = p.duplex ?? p.portDuplex ?? p._raw?.duplex ?? p._raw?.portDuplex ?? p._raw?.linkDuplex;
    const status = p.status || p.operStatus || p._raw?.operStatus || p._raw?.linkStatus || '';
    const poeUsed    = p.poeUsed    ?? p._raw?.poeUsed;
    const poeEnabled = p.poeEnabled ?? p._raw?.poeEnabled;
    if (speed != null || duplex || status) {
      const portLabel = p.portName || p.name || (hop.ingress_port || '');
      body.innerHTML += `<div class="subsection-title">Port Info (R1)${portLabel ? ' — ' + esc(portLabel) : ''}</div>`;
      const rows = [
        ['Status', status || '–', statusColor(status)],
        ['Speed',  speed  != null ? speed + ' Mbps' : '–'],
        ['Duplex', duplex || '–', duplex && duplex.toLowerCase().includes('half') ? 'warn' : 'ok'],
      ];
      if (poeEnabled != null) rows.push(['PoE Enabled', poeEnabled ? 'Yes' : 'No']);
      if (poeUsed   != null) rows.push(['PoE Used',    poeUsed + ' W']);
      body.appendChild(buildDetailGrid(rows));
    }
  }

  // AP switch uplink — port status, errors and PoE sourced from the connecting Cisco port
  if (hop.device_type === 'ruckus_ap' && hop.raw_data && hop.raw_data.switch_port) {
    const rd = hop.raw_data;
    body.innerHTML += `<div class="subsection-title">Switch Uplink Port — ${esc(rd.switch_port)}</div>`;

    if (rd.switch_int_status) {
      const s = rd.switch_int_status;
      body.appendChild(buildDetailGrid([
        ['Status', s.status || '–', statusColor(s.status)],
        ['Speed',  s.speed  || '–'],
        ['Duplex', s.duplex || '–', s.duplex && s.duplex.includes('half') ? 'warn' : 'ok'],
        ['VLAN',   s.vlan   || '–'],
      ]));
    }

    if (rd.switch_int_details) {
      const d = rd.switch_int_details;
      body.appendChild(buildDetailGrid([
        ['Input Errors',  d.input_errors,  d.input_errors  > 0 ? 'warn' : 'ok'],
        ['Output Errors', d.output_errors, d.output_errors > 0 ? 'warn' : 'ok'],
        ['CRC Errors',    d.crc_errors,    d.crc_errors    > 0 ? 'crit' : 'ok'],
        ['Runts',         d.runts,         d.runts         > 0 ? 'warn' : 'ok'],
      ]));
    }

    if (rd.switch_poe) {
      const p = rd.switch_poe;
      body.innerHTML += `<div class="subsection-title">PoE</div>`;
      body.appendChild(buildDetailGrid([
        ['Status', p.operational || '–', p.operational && p.operational.toLowerCase().includes('deny') ? 'crit' : 'ok'],
        ['Power',  p.power_watts ? p.power_watts + ' W' : '–'],
        ['Max',    p.max_watts   ? p.max_watts   + ' W' : '–'],
        ['Class',  p.poe_class   || '–'],
      ]));
    }
  }

  // Wireless info
  if (hop.device_type === 'wireless_client' && hop.raw_data) {
    const rd = hop.raw_data;
    if (rd.ssid || rd.rssi) {
      body.innerHTML += `<div class="subsection-title">Wireless</div>`;
      body.appendChild(buildDetailGrid([
        ['SSID',  rd.ssid || '–'],
        ['RSSI',  rd.rssi ? rd.rssi + ' dBm' : '–', rssiColor(rd.rssi)],
        ['MAC',   rd.mac || '–'],
      ]));
    }
  }

  // Per-hop tests
  if (hop.tests && hop.tests.length) {
    const nonSkip = hop.tests.filter(t => t.status !== 'skip' && t.status !== 'na');
    if (nonSkip.length) {
      body.innerHTML += `<div class="subsection-title">Tests</div>`;
      const testGrid = document.createElement('div');
      testGrid.className = 'tests-grid compact';
      nonSkip.forEach(test => {
        const item = document.createElement('div');
        item.className = `test-item test-${test.status}`;
        const icon = { pass: '✓', fail: '✗', warning: '⚠' }[test.status] || '–';
        item.innerHTML = `
          <span class="test-icon test-icon-${test.status}">${icon}</span>
          <div class="test-body">
            <div class="test-name">${esc(test.name)}</div>
            ${test.value ? `<div class="test-value">${esc(test.value)}</div>` : ''}
          </div>`;
        testGrid.appendChild(item);
      });
      body.appendChild(testGrid);
    }
  }

  // FortiGate egress interface stats (from SSH)
  if (hop.device_type === 'firewall' && hop.raw_data && hop.raw_data.interface_stats) {
    const s = hop.raw_data.interface_stats;
    const statKeys = Object.keys(s).filter(k => !['mtu', 'lag_parent'].includes(k));
    if (statKeys.length || s.mtu) {
      // If the port is a LAG member, stats come from the parent aggregate interface
      const portLabel = s.lag_parent
        ? `${hop.egress_port || ''} → ${s.lag_parent} (LAG)`
        : (hop.egress_port || '');
      body.innerHTML += `<div class="subsection-title">Egress Interface (${esc(portLabel)})</div>`;

      // Detect software / zone interface (MTU present but all traffic counters are 0)
      const allZero = statKeys.every(k => (s[k] ?? 0) === 0);
      if (allZero && s.mtu) {
        body.innerHTML += `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
          ℹ️ Software or zone interface — traffic counters not maintained by the OS.
          ${s.mtu ? `MTU: ${s.mtu} bytes.` : ''}
        </div>`;
      } else {
        body.appendChild(buildDetailGrid([
          ['RX Packets', s.rx_packets != null ? s.rx_packets.toLocaleString() : '–'],
          ['TX Packets', s.tx_packets != null ? s.tx_packets.toLocaleString() : '–'],
          ['RX Bytes',   s.rx_bytes   != null ? fmtBps(s.rx_bytes)  : '–'],
          ['TX Bytes',   s.tx_bytes   != null ? fmtBps(s.tx_bytes)  : '–'],
          ['RX Errors',  s.rx_errors  != null ? s.rx_errors  : '–', s.rx_errors  > 0 ? 'warn' : 'ok'],
          ['TX Errors',  s.tx_errors  != null ? s.tx_errors  : '–', s.tx_errors  > 0 ? 'warn' : 'ok'],
          ['RX Drops',   s.rx_drops   != null ? s.rx_drops   : '–', s.rx_drops   > 0 ? 'warn' : 'ok'],
          ['TX Drops',   s.tx_drops   != null ? s.tx_drops   : '–', s.tx_drops   > 0 ? 'warn' : 'ok'],
          ['MTU',        s.mtu ? s.mtu + ' bytes' : '–'],
        ]));
      }
    }
  }

  // Port-channel member links
  if (hop.raw_data && hop.raw_data.etherchannel_members && hop.raw_data.etherchannel_members.length) {
    body.innerHTML += `<div class="subsection-title">Port-Channel Members</div>`;
    const rows = hop.raw_data.etherchannel_members.map(m => [
      m.port, m.status, m.status === 'bundled' ? 'ok' : 'crit'
    ]);
    body.appendChild(buildDetailGrid(rows));
  }

  // Uplink interface error counters (Cisco side of links to upstream devices, e.g. Ruckus)
  if (hop.raw_data && hop.raw_data.uplink_details && Object.keys(hop.raw_data.uplink_details).length) {
    body.innerHTML += `<div class="subsection-title">Uplink Port Counters</div>`;
    Object.entries(hop.raw_data.uplink_details).forEach(([port, d]) => {
      const hasErrors = d.crc_errors > 0 || d.input_errors > 0 || d.output_errors > 0;
      body.appendChild(buildDetailGrid([
        [`${port} CRC`,   d.crc_errors,    d.crc_errors   > 0 ? 'crit' : 'ok'],
        [`${port} In Err`,d.input_errors,  d.input_errors > 0 ? 'warn' : 'ok'],
        [`${port} Out Err`,d.output_errors,d.output_errors > 0 ? 'warn' : 'ok'],
        [`${port} MTU`,   d.mtu ? d.mtu + 'b' : '–'],
      ]));
    });
  }

  // Raw error
  if (hop.raw_data && hop.raw_data.error) {
    body.innerHTML += `<div class="subsection-title">Connection Error</div>
      <div style="color:var(--crit);font-size:12px;font-family:monospace;padding:8px 0">${esc(hop.raw_data.error)}</div>`;
  }

  // System logs captured during SSH session
  if (hop.system_logs && hop.system_logs.length) {
    body.innerHTML += `<div class="subsection-title">System Logs</div>`;
    const logList = document.createElement('div');
    logList.className = 'system-logs';
    hop.system_logs.forEach(entry => {
      const row = document.createElement('div');
      const sevCls = entry.severity === 'CRIT' ? 'log-crit'
                   : entry.severity === 'ERR'  ? 'log-err'
                   : 'log-warn';
      row.className = `log-entry ${sevCls}`;
      row.innerHTML = `<span class="log-sev">${esc(entry.severity)}</span><span class="log-msg">${esc(entry.message)}</span>`;
      logList.appendChild(row);
    });
    body.appendChild(logList);
  }

  // Issues for this hop
  if (hop.issues && hop.issues.length) {
    body.innerHTML += `<div class="subsection-title">Issues on this hop</div>`;
    const issueList = document.createElement('div');
    issueList.className = 'hop-issues';
    hop.issues.forEach(issue => {
      const item = document.createElement('div');
      item.className = `issue-item ${issue.severity}`;
      item.innerHTML = `
        <span class="issue-sev ${issue.severity}">${issue.severity}</span>
        <div class="issue-body">
          <div class="issue-msg">${esc(issue.message)}</div>
          ${issue.detail ? `<div class="issue-detail">${esc(issue.detail)}</div>` : ''}
        </div>`;
      issueList.appendChild(item);
    });
    body.appendChild(issueList);
  }

  card.appendChild(header);
  card.appendChild(body);

  // Auto-open if has issues
  if (hasCrit || hasWarn) card.classList.add('open');

  return card;
}

// ── Helpers ───────────────────────────────────────────────────
function buildDetailGrid(rows) {
  const grid = document.createElement('div');
  grid.className = 'detail-grid';
  rows.forEach(([label, value, colorClass]) => {
    if (value === undefined || value === null || value === '') return;
    const item = document.createElement('div');
    item.className = 'detail-item';
    item.innerHTML = `
      <div class="detail-label">${esc(String(label))}</div>
      <div class="detail-value ${colorClass || ''}">${esc(String(value))}</div>`;
    grid.appendChild(item);
  });
  return grid;
}

function scrollToHop(idx) {
  const el = document.getElementById(`hop-${idx}`);
  if (!el) return;
  el.classList.add('open');
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function statusColor(status) {
  if (!status) return '';
  if (status === 'connected')  return 'ok';
  if (status === 'err-disabled' || status === 'disabled') return 'crit';
  return 'warn';
}

function rssiColor(rssi) {
  if (!rssi) return '';
  const v = parseInt(rssi);
  if (v >= -60) return 'ok';
  if (v >= -75) return 'warn';
  return 'crit';
}

function fmtMtu(mtu, rawData) {
  if (!mtu) return '–';
  const sysMtu = rawData && rawData.system_mtu && rawData.system_mtu.system_mtu;
  const jumbo  = rawData && rawData.system_mtu && rawData.system_mtu.jumbo_mtu;
  if (sysMtu && mtu === sysMtu) return `${mtu} bytes (global default)`;
  if (jumbo  && mtu === jumbo)  return `${mtu} bytes (jumbo global)`;
  return `${mtu} bytes (interface override)`;
}

function fmtBps(bps) {
  if (!bps) return '0 bps';
  if (bps >= 1e9) return (bps / 1e9).toFixed(1) + ' Gbps';
  if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' Mbps';
  if (bps >= 1e3) return (bps / 1e3).toFixed(1) + ' Kbps';
  return bps + ' bps';
}

function getDeviceColor(type, alpha) {
  const map = {
    firewall:        `rgba(249,115,22,${alpha||1})`,
    cisco_switch:    `rgba(59,130,246,${alpha||1})`,
    ruckus_switch:   `rgba(6,182,212,${alpha||1})`,
    ruckus_ap:       `rgba(139,92,246,${alpha||1})`,
    wireless_client: `rgba(34,197,94,${alpha||1})`,
    wired_client:    `rgba(34,197,94,${alpha||1})`,
    unknown:         `rgba(100,116,139,${alpha||1})`,
  };
  return map[type] || map.unknown;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
