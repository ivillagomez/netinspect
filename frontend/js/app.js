'use strict';

// ── Constants ─────────────────────────────────────────────────
const DEVICE_META = {
  firewall:         { icon: '🔥', label: 'Firewall',      cls: 'fw'       },
  cisco_switch:     { icon: '🔌', label: 'Cisco Switch',  cls: 'cisco_sw' },
  ruckus_switch:    { icon: '🌐', label: 'Ruckus Switch', cls: 'r1_sw'    },
  ruckus_ap:        { icon: '📡', label: 'Access Point',  cls: 'ap'       },
  wireless_client:  { icon: '💻', label: 'WiFi Client',   cls: 'client'   },
  wired_client:     { icon: '🖥️', label: 'Wired Device',  cls: 'client'   },
  unknown:          { icon: '❓', label: 'Unknown',       cls: 'unknown'  },
};

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadDeviceSummary();
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') doTrace();
  });
});

async function loadDeviceSummary() {
  try {
    const res = await fetch('/api/devices');
    const data = await res.json();
    const el = document.getElementById('deviceSummary');
    el.innerHTML = '';
    if (data.fortigate) el.appendChild(mkBadge('🔥 ' + data.fortigate.host, 'neutral'));
    if (data.cisco_switches) {
      data.cisco_switches.forEach(sw =>
        el.appendChild(mkBadge('🔌 ' + sw.name, 'neutral'))
      );
    }
    if (data.ruckus_r1) el.appendChild(mkBadge('📡 R1 Cloud', 'neutral'));
  } catch (_) {}
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
  const keys = ['interface_status', 'error_counters', 'mtu_check', 'stp', 'poe', 'neighbor_info'];
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
    wireless_info:    true,
  };
}

// ── Trace ─────────────────────────────────────────────────────
async function doTrace() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;

  setState('loading');

  try {
    const res = await fetch('/api/trace', {
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
    iconWrap.textContent = meta.icon;

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

    node.appendChild(iconWrap);
    node.appendChild(label);
    node.appendChild(sub);
    if (portText) node.appendChild(portInfo);
    flow.appendChild(node);

    if (idx < path.length - 1) {
      const arrow = document.createElement('div');
      arrow.className = 'path-arrow';

      // Show connection ports between this hop and the next
      const nextHop = path[idx + 1];
      const connLabel = buildConnLabel(hop, nextHop);

      if (connLabel) {
        const lbl = document.createElement('div');
        lbl.className = 'arrow-conn-label';
        lbl.textContent = connLabel;
        arrow.appendChild(lbl);
      }
      const line = document.createElement('div');
      line.className = 'arrow-line';
      arrow.appendChild(line);
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
  if (from && to) return `${from} ↔ ${to}`;
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
  hopIcon.textContent = meta.icon;
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
      ['MTU',            d.mtu ? d.mtu + ' bytes' : '–', d.mtu && d.mtu !== 1500 ? 'warn' : ''],
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

  // Raw error
  if (hop.raw_data && hop.raw_data.error) {
    body.innerHTML += `<div class="subsection-title">Connection Error</div>
      <div style="color:var(--crit);font-size:12px;font-family:monospace;padding:8px 0">${esc(hop.raw_data.error)}</div>`;
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
