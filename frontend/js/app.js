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

// ── Module-level state ────────────────────────────────────────
let _caps = {};   // last-known capabilities; updated by initUI()

// ── Constants ─────────────────────────────────────────────────
const VENDOR_PATH_META = {
  firewall:       { label: 'FortiGate',  color: 'var(--fw-color)'      },
  cisco_switch:   { label: 'Cisco',      color: 'var(--sw-color)'      },
  ruckus_switch:  { label: 'Ruckus ICX', color: 'var(--r1sw-color)'    },
  ruckus_ap:      { label: 'Ruckus AP',  color: 'var(--ap-color)'      },
  aruba_switch:   { label: 'Aruba',      color: 'var(--aruba-color)'   },
  aruba_ap:       { label: 'Aruba AP',   color: 'var(--aruba-color)'   },
  extreme_switch: { label: 'Extreme',    color: 'var(--extreme-color)' },
};

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

// ── Trace state ───────────────────────────────────────────────
let _lastResult = null;   // most recent TraceResult JSON
let _lastQuery  = '';     // most recent search query

// ── Profile state ─────────────────────────────────────────────
let _activeProfileName = null;   // name of last-loaded profile (null = unknown/modified)

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
  initEventHandlers();
  _renderHistoryPanel(_loadHistoryEntries());
});

// Wire up all event handlers in JavaScript so the page works under a strict
// Content-Security-Policy (script-src 'self') that blocks inline onclick= attrs.
function initEventHandlers() {
  // ── Header ────────────────────────────────────────────────
  document.querySelector('.header-settings-btn')
    ?.addEventListener('click', openSettings);
  document.getElementById('themeToggle')
    ?.addEventListener('click', toggleTheme);

  // ── Search ────────────────────────────────────────────────
  document.getElementById('traceBtn')
    ?.addEventListener('click', doTrace);
  document.getElementById('searchInput')
    ?.addEventListener('keydown', e => { if (e.key === 'Enter') doTrace(); });
  document.querySelectorAll('.search-examples code')
    .forEach(el => el.addEventListener('click', function () { fillExample(this); }));

  // ── Diagnostics options panel ─────────────────────────────
  document.querySelector('.options-toggle')
    ?.addEventListener('click', toggleOptions);
  ['opt_interface_status', 'opt_error_counters', 'opt_mtu_check',
   'opt_stp', 'opt_poe', 'opt_neighbor_info', 'opt_system_logs']
    .forEach(id => document.getElementById(id)
      ?.addEventListener('change', updateOptionsLabel));

  // ── Settings modal ────────────────────────────────────────
  document.getElementById('settingsOverlay')
    ?.addEventListener('click', closeSettingsOnBackdrop);
  document.querySelector('.settings-close')
    ?.addEventListener('click', closeSettings);
  document.querySelectorAll('.settings-section-hd')
    .forEach(el => el.addEventListener('click', function () { toggleSettingsSection(this); }));
  document.getElementById('addCiscoBtn')
    ?.addEventListener('click', () => addSwitchRow('cisco'));
  document.getElementById('addArubaBtn')
    ?.addEventListener('click', () => addSwitchRow('aruba'));
  document.getElementById('settingsCancelBtn')
    ?.addEventListener('click', closeSettings);
  document.getElementById('settingsSaveBtn')
    ?.addEventListener('click', saveSettings);
  document.getElementById('settingsClearBtn')
    ?.addEventListener('click', clearSettings);

  // ── Discovery ─────────────────────────────────────────────
  document.getElementById('disc_protocol')
    ?.addEventListener('change', discUpdateProtocolFields);
  document.getElementById('discStartBtn')
    ?.addEventListener('click', startDiscovery);
  document.getElementById('discStopBtn')
    ?.addEventListener('click', stopDiscovery);
  document.getElementById('discSelectAll')
    ?.addEventListener('change', function () { discToggleAll(this.checked); });
  document.getElementById('discAddBtn')
    ?.addEventListener('click', addDiscoveredDevices);

  // ── Export bar ────────────────────────────────────────────
  document.getElementById('exportCsvBtn')
    ?.addEventListener('click', downloadCsv);
  document.getElementById('exportPrintBtn')
    ?.addEventListener('click', () => window.print());

  // ── History panel ─────────────────────────────────────────
  document.querySelector('.history-header')
    ?.addEventListener('click', toggleHistory);
  document.getElementById('historyClearBtn')
    ?.addEventListener('click', clearHistory);

  // ── No-config banner ──────────────────────────────────────
  document.getElementById('noConfigHintBtn')
    ?.addEventListener('click', openSettings);

  // ── Profile selector ──────────────────────────────────────
  document.getElementById('profileBtn')
    ?.addEventListener('click', toggleProfileDropdown);
  document.getElementById('profileSaveBtn')
    ?.addEventListener('click', _openSaveProfileForm);
  document.getElementById('profileSaveConfirmBtn')
    ?.addEventListener('click', _confirmSaveProfile);
  document.getElementById('profileSaveCancelBtn')
    ?.addEventListener('click', _cancelSaveProfileForm);
  document.getElementById('profileNameInput')
    ?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')  _confirmSaveProfile();
      if (e.key === 'Escape') _cancelSaveProfileForm();
    });
  // Event delegation: one persistent listener on the list container handles
  // all load/delete clicks even as items are re-rendered asynchronously.
  document.getElementById('profileList')
    ?.addEventListener('click', _handleProfileListClick);
  // Close dropdown when clicking outside the selector
  document.addEventListener('click', (e) => {
    if (!document.getElementById('profileSelector')?.contains(e.target)) {
      closeProfileDropdown();
    }
  });
}

async function initUI() {
  let caps = {};
  let uiCfg = {};
  try {
    const [capsRes, cfgRes] = await Promise.all([
      fetch('/api/capabilities'),
      fetch('/api/ui-config'),
    ]);
    if (capsRes.ok) caps   = await capsRes.json();
    if (cfgRes.ok)  uiCfg  = await cfgRes.json();
  } catch (_) { /* server unreachable — show nothing */ }

  _caps = caps;   // cache for later use (e.g. after settings save)

  // Update footer version label if served version is available
  if (uiCfg.version) {
    const vEl = document.getElementById('versionLabel');
    if (vEl) vEl.textContent = 'v' + uiCfg.version;
  }

  renderVendorBar(caps);
  updateSearchHints(caps);
  _updateConfigBanner(caps);
}

// Show/hide the "No devices configured" warning below the search examples.
// The banner is visible when none of the known capability flags are truthy.
function _updateConfigBanner(caps = {}) {
  const hint = document.getElementById('noConfigHint');
  if (!hint) return;
  const hasAny = Object.values(caps).some(Boolean);
  hint.style.display = hasAny ? 'none' : '';
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

  // deviceSummary was moved to Settings button in header — no-op for visible chips
  // (updateSearchHints below still uses `caps` to adjust placeholder / examples)
}

function updateSearchHints(caps = {}) {
  const parts = ['MAC address', 'IP address'];
  if (caps.fortigate) parts.push('FortiGate address name');
  document.getElementById('searchInput').placeholder = parts.join('  ·  ');

  // Add FortiGate address name example only when FG is configured
  const exRow = document.querySelector('.search-examples');
  if (exRow && caps.fortigate && !exRow.querySelector('[data-fg-example]')) {
    const code = document.createElement('code');
    code.setAttribute('data-fg-example', '1');
    code.textContent = 'Server-Web-01';
    code.addEventListener('click', function () { fillExample(this); });
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

// ── Settings modal ────────────────────────────────────────────
const _MASKED = '••••••••';
let _settingsData = null;   // last-fetched config from server

function toggleSettingsSection(hd) {
  hd.classList.toggle('open');
  const bd = hd.nextElementSibling;
  bd.classList.toggle('open');
}

function openSettings() {
  document.getElementById('settingsOverlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  _loadSettings();
}

function closeSettings() {
  document.getElementById('settingsOverlay').classList.add('hidden');
  document.body.style.overflow = '';
}

function closeSettingsOnBackdrop(e) {
  if (e.target === document.getElementById('settingsOverlay')) closeSettings();
}

async function _loadSettings() {
  const msg = document.getElementById('settingsSaveMsg');
  msg.className = 'settings-save-msg hidden';

  try {
    const res = await apiFetch('/api/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _settingsData = await res.json();
    _populateSettings(_settingsData);
  } catch(e) {
    msg.textContent = 'Could not load settings: ' + e.message;
    msg.className = 'settings-save-msg err';
  }
}

function _populateSettings(d) {
  // ── Global switch credentials ──────────────────────────────
  const sc = d.switch_credentials || {};
  _setVal('cfg_sw_username',    sc.username    || '');
  _setVal('cfg_sw_password',    sc.password    || '');
  _setVal('cfg_sw_device_type', sc.device_type || 'cisco_ios');

  // ── Cisco switches ─────────────────────────────────────────
  _renderSwitchList('cisco', d.cisco_switches || []);

  // ── Aruba switches ─────────────────────────────────────────
  _renderSwitchList('aruba', d.aruba_switches || []);

  // ── FortiGate ──────────────────────────────────────────────
  const fg = d.fortigate || {};
  _setVal('cfg_fg_host',     fg.host          || '');
  _setVal('cfg_fg_port',     fg.port          || 443);
  _setVal('cfg_fg_token',    fg.access_token  || '');
  _setVal('cfg_fg_ssl',      fg.verify_ssl === false ? 'false' : 'true');
  _setVal('cfg_fg_ssh_user', fg.ssh_username  || '');
  _setVal('cfg_fg_ssh_pass', fg.ssh_password  || '');
  _setVal('cfg_fg_ssh_port', fg.ssh_port      || 22);

  // ── Ruckus One ─────────────────────────────────────────────
  const r1 = d.ruckus_r1 || {};
  _setVal('cfg_r1_region',        r1.base_url      || 'https://api.ruckus.cloud');
  _setVal('cfg_r1_tenant',        r1.tenant_id     || '');
  _setVal('cfg_r1_client_id',     r1.client_id     || '');
  _setVal('cfg_r1_client_secret', r1.client_secret || '');

  // ── Aruba Central ──────────────────────────────────────────
  const ac = d.aruba_central || {};
  _setVal('cfg_ac_customer_id',   ac.customer_id   || '');
  _setVal('cfg_ac_client_id',     ac.client_id     || '');
  _setVal('cfg_ac_client_secret', ac.client_secret || '');

  // ── ExtremeCloud IQ ────────────────────────────────────────
  const xiq = d.extreme_iq || {};
  _setVal('cfg_xiq_api_key', xiq.api_key  || '');

  // ── Server ─────────────────────────────────────────────────
  const srv = d.server || {};
  _setVal('cfg_srv_host',    srv.host    || '0.0.0.0');
  _setVal('cfg_srv_port',    srv.port    || 8080);
  _setVal('cfg_srv_api_key', srv.api_key || '');
  _setVal('cfg_srv_origins', (srv.allowed_origins || []).join(', '));
}

function _setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

// ── Switch list rendering ──────────────────────────────────────
function _renderSwitchList(type, switches) {
  const container = document.getElementById(type + '_switches_list');
  if (!container) return;
  container.innerHTML = '';
  switches.forEach((sw, i) => _appendSwitchRow(type, sw, i));
}

function _appendSwitchRow(type, sw = {}, idx) {
  const container = document.getElementById(type + '_switches_list');
  const isAruba = type === 'aruba';
  const driverOpts = isAruba
    ? `<option value="aruba_os"${sw.os_type === 'aruba_os' || !sw.os_type ? ' selected' : ''}>aruba_os</option>
       <option value="aruba_osix"${sw.os_type === 'aruba_osix' ? ' selected' : ''}>aruba_osix</option>`
    : `<option value="cisco_ios"${sw.device_type === 'cisco_ios' || !sw.device_type ? ' selected' : ''}>cisco_ios</option>
       <option value="cisco_xe"${sw.device_type === 'cisco_xe' ? ' selected' : ''}>cisco_xe</option>`;
  const driverKey = isAruba ? 'os_type' : 'device_type';

  const row = document.createElement('div');
  row.className = 'settings-switch-row';
  row.dataset.swtype = type;
  row.innerHTML = `
    <div class="settings-field"><label>Name</label>
      <input type="text" class="sw-name" value="${esc(sw.name || '')}" placeholder="core-sw-01" autocomplete="off" spellcheck="false">
    </div>
    <div class="settings-field"><label>Host / IP</label>
      <input type="text" class="sw-host" value="${esc(sw.host || '')}" placeholder="e.g. 10.0.0.1" autocomplete="off" spellcheck="false">
    </div>
    <div class="settings-field settings-field--sm"><label>Username <span style="opacity:.5">(override)</span></label>
      <input type="text" class="sw-username" value="${esc(sw.username || '')}" placeholder="from global" autocomplete="off" spellcheck="false">
    </div>
    <div class="settings-field settings-field--sm"><label>Password <span style="opacity:.5">(override)</span></label>
      <input type="password" class="sw-password" value="${esc(sw.password || '')}" placeholder="from global" autocomplete="new-password">
    </div>
    <div class="settings-field settings-field--sm"><label>Driver</label>
      <select class="sw-driver">${driverOpts}</select>
    </div>
    ${!isAruba ? `<div class="settings-field settings-field--sm"><label>SNMP community</label>
      <input type="text" class="sw-snmp" value="${esc(sw.snmp_community || '')}" placeholder="public" autocomplete="off" spellcheck="false">
    </div>` : ''}
    <button class="settings-switch-remove" title="Remove">✕</button>
  `;
  row.querySelector('.settings-switch-remove')
    .addEventListener('click', () => row.remove());
  container.appendChild(row);
}

function addSwitchRow(type) {
  _appendSwitchRow(type, {});
}

function removeSwitchRow(btn) {
  btn.closest('.settings-switch-row').remove();
}

// ── Collect + save ─────────────────────────────────────────────
async function saveSettings() {
  const btn = document.getElementById('settingsSaveBtn');
  const msg = document.getElementById('settingsSaveMsg');
  btn.disabled = true;
  msg.className = 'settings-save-msg hidden';

  try {
    const body = _collectSettings();

    // ── Client-side validation ─────────────────────────────────
    const warnings = [];
    const fgToken   = document.getElementById('cfg_fg_token')?.value.trim();
    const fgSshUser = document.getElementById('cfg_fg_ssh_user')?.value.trim();
    if ((fgToken || fgSshUser) && !body.fortigate) {
      warnings.push('FortiGate: Host / IP is required to save credentials.');
    }
    if (warnings.length) {
      msg.textContent = '⚠ ' + warnings.join('  ');
      msg.className = 'settings-save-msg err';
      btn.disabled = false;
      return;
    }

    const res = await apiFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    msg.textContent = '✓ ' + data.message;
    msg.className = 'settings-save-msg ok';
    // Config was modified — clear the active profile indicator so the button
    // no longer shows a profile name that may no longer match what's on disk.
    _activeProfileName = null;
    _updateProfileBtnLabel();
    // Refresh capabilities bar since config changed
    initUI();
  } catch(e) {
    msg.textContent = '✗ ' + e.message;
    msg.className = 'settings-save-msg err';
  } finally {
    btn.disabled = false;
    // Scroll to message
    document.getElementById('settingsSaveMsg').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function clearSettings() {
  const msg = document.getElementById('settingsSaveMsg');
  if (!confirm('Clear ALL settings?\n\nThis will remove all configured devices and credentials from the form. Click Save Changes afterwards to write the empty config to disk.')) return;
  _populateSettings({});
  msg.textContent = 'All fields cleared — click Save Changes to apply.';
  msg.className = 'settings-save-msg ok';
  document.getElementById('settingsSaveMsg').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Config profiles ────────────────────────────────────────────

function toggleProfileDropdown() {
  const dd = document.getElementById('profileDropdown');
  if (!dd) return;
  if (dd.classList.contains('hidden')) {
    loadProfiles();   // refresh list on open
    dd.classList.remove('hidden');
  } else {
    dd.classList.add('hidden');
  }
}

function closeProfileDropdown() {
  document.getElementById('profileDropdown')?.classList.add('hidden');
  _cancelSaveProfileForm();   // always reset inline form so it's clean on next open
}

async function loadProfiles() {
  const list = document.getElementById('profileList');
  if (!list) return;
  try {
    const res = await apiFetch('/api/profiles');
    if (!res.ok) return;
    const data = await res.json();
    _renderProfileList(data.profiles || []);
  } catch (_) { /* network error — silently skip */ }
}

function _renderProfileList(profiles) {
  const list = document.getElementById('profileList');
  const sep  = document.getElementById('profileDropdownSep');
  if (!list) return;
  list.innerHTML = '';

  if (profiles.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'profile-empty';
    empty.textContent = 'No profiles saved yet';
    list.appendChild(empty);
    if (sep) sep.style.display = 'none';
    return;
  }

  if (sep) sep.style.display = '';
  // Use data-* attributes instead of per-element addEventListener so that
  // the single delegated listener on #profileList (added in initEventHandlers)
  // handles all clicks — this is robust against list re-renders.
  profiles.forEach(name => {
    const isActive = name === _activeProfileName;
    const item = document.createElement('div');
    item.className = 'profile-item' + (isActive ? ' profile-item--active' : '');

    const loadBtn = document.createElement('button');
    loadBtn.className = 'profile-item-load';
    loadBtn.dataset.profileAction = 'load';
    loadBtn.dataset.profileName   = name;
    loadBtn.title = isActive ? 'Currently active' : 'Load this profile';
    loadBtn.innerHTML = esc(name) + (isActive ? ' <span class="profile-check" style="pointer-events:none">✓</span>' : '');

    const delBtn = document.createElement('button');
    delBtn.className = 'profile-item-delete';
    delBtn.dataset.profileAction = 'delete';
    delBtn.dataset.profileName   = name;
    delBtn.title = 'Delete profile';
    delBtn.textContent = '✕';

    item.appendChild(loadBtn);
    item.appendChild(delBtn);
    list.appendChild(item);
  });
}

// Delegated click handler for the profile list — handles both load and delete.
// Using delegation means only ONE listener lives on the static #profileList
// element; it catches clicks on all dynamically rendered profile buttons.
function _handleProfileListClick(e) {
  const btn = e.target.closest('[data-profile-action]');
  if (!btn) return;
  e.stopPropagation();   // prevent the "outside click" document handler from firing
  const action = btn.dataset.profileAction;
  const name   = btn.dataset.profileName;
  if (!name) return;
  if (action === 'load')   activateProfile(name);
  if (action === 'delete') deleteProfile(name);
}

async function activateProfile(name) {
  closeProfileDropdown();
  // No confirm() — the user deliberately chose this profile from the dropdown.
  // The toast notification confirms what happened.
  try {
    const res = await apiFetch(`/api/profiles/${encodeURIComponent(name)}/load`, { method: 'PUT' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    _activeProfileName = name;
    _updateProfileBtnLabel();
    // Clear trace history — it belongs to the previous environment, not this profile.
    localStorage.removeItem(_HISTORY_KEY);
    _renderHistoryPanel([]);
    initUI();   // refresh capabilities bar
    _showProfileToast(`✓ Profile "${name}" loaded`);
  } catch (e) {
    _showProfileToast(`✗ Load failed: ${e.message}`, true);
  }
}

function _openSaveProfileForm() {
  // Swap the "Save as Profile…" button for the inline name input — no prompt() needed.
  document.getElementById('profileSaveBtn')?.classList.add('hidden');
  const form = document.getElementById('profileSaveForm');
  form?.classList.remove('hidden');
  const input = document.getElementById('profileNameInput');
  if (input) { input.value = ''; input.focus(); }
}

function _cancelSaveProfileForm() {
  document.getElementById('profileSaveForm')?.classList.add('hidden');
  document.getElementById('profileSaveBtn')?.classList.remove('hidden');
}

async function _confirmSaveProfile() {
  const input = document.getElementById('profileNameInput');
  const name  = (input?.value || '').trim();
  if (!name) { input?.focus(); return; }
  if (name.length > 50) {
    _showProfileToast('✗ Profile name too long (max 50 chars).', true);
    input?.focus();
    return;
  }
  _cancelSaveProfileForm();   // reset UI immediately
  closeProfileDropdown();
  try {
    const res = await apiFetch(`/api/profiles/${encodeURIComponent(name)}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    _activeProfileName = name;
    _updateProfileBtnLabel();
    _showProfileToast(`✓ Profile "${name}" saved`);
  } catch (e) {
    _showProfileToast(`✗ Save failed: ${e.message}`, true);
  }
}

// saveAsProfile kept as a no-op alias so any stale references don't crash
function saveAsProfile() { _openSaveProfileForm(); }

async function deleteProfile(name) {
  closeProfileDropdown();
  try {
    const res = await apiFetch(`/api/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (_activeProfileName === name) {
      _activeProfileName = null;
      _updateProfileBtnLabel();
    }
    _showProfileToast(`Profile "${name}" deleted`);
    loadProfiles();   // refresh dropdown list
  } catch (e) {
    _showProfileToast(`✗ Delete failed: ${e.message}`, true);
  }
}

function _updateProfileBtnLabel() {
  const lbl = document.getElementById('profileBtnLabel');
  if (!lbl) return;
  // Truncate long names so the button stays compact
  const display = _activeProfileName
    ? (_activeProfileName.length > 20 ? _activeProfileName.slice(0, 18) + '…' : _activeProfileName)
    : 'Profiles';
  lbl.textContent = display;
}

function _showProfileToast(message, isError = false) {
  let toast = document.getElementById('profileToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'profileToast';
    toast.className = 'profile-toast';
    document.querySelector('.app')?.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.toggle('profile-toast--error', isError);
  toast.classList.add('profile-toast--visible');
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => toast.classList.remove('profile-toast--visible'), 3000);
}

function _collectSettings() {
  const v = id => document.getElementById(id)?.value.trim() || '';

  // ── Global switch credentials ──────────────────────────────
  const swUser = v('cfg_sw_username');
  const swPass = v('cfg_sw_password');
  const switch_credentials = (swUser || swPass) ? {
    username:    swUser,
    password:    swPass || _MASKED,   // keep existing if blank
    device_type: v('cfg_sw_device_type') || 'cisco_ios',
    timeout: 30,
  } : null;

  // ── Switch helper ──────────────────────────────────────────
  const collectSwitches = (type) => {
    const isAruba = type === 'aruba';
    return Array.from(
      document.querySelectorAll(`#${type}_switches_list .settings-switch-row`)
    ).map(row => {
      const get = cls => row.querySelector(cls)?.value.trim() || '';
      const name = get('.sw-name');
      const host = get('.sw-host');
      if (!name && !host) return null;   // skip empty rows
      const entry = {
        name,
        host,
        username: get('.sw-username') || undefined,
        password: get('.sw-password') || _MASKED,
        timeout: 30,
      };
      if (isAruba) {
        entry.os_type = get('.sw-driver') || 'aruba_os';
      } else {
        entry.device_type  = get('.sw-driver') || 'cisco_ios';
        const snmp = get('.sw-snmp');
        if (snmp) entry.snmp_community = snmp;
      }
      // Strip undefined fields
      Object.keys(entry).forEach(k => entry[k] === undefined && delete entry[k]);
      return entry;
    }).filter(Boolean);
  };

  // ── FortiGate ──────────────────────────────────────────────
  const fgHost = v('cfg_fg_host');
  const fortigate = fgHost ? {
    host:         fgHost,
    port:         parseInt(v('cfg_fg_port')) || 443,
    access_token: v('cfg_fg_token') || _MASKED,
    verify_ssl:   document.getElementById('cfg_fg_ssl')?.value !== 'false',
    ssh_username: v('cfg_fg_ssh_user') || undefined,
    ssh_password: v('cfg_fg_ssh_pass') || _MASKED,
    ssh_port:     parseInt(v('cfg_fg_ssh_port')) || 22,
  } : null;
  if (fortigate) Object.keys(fortigate).forEach(k => fortigate[k] === undefined && delete fortigate[k]);

  // ── Ruckus One ─────────────────────────────────────────────
  const r1ClientId = v('cfg_r1_client_id');
  const r1Tenant   = v('cfg_r1_tenant');
  const ruckus_r1 = (r1ClientId || r1Tenant) ? {
    base_url:      v('cfg_r1_region') || 'https://api.ruckus.cloud',
    tenant_id:     r1Tenant           || undefined,
    client_id:     r1ClientId         || undefined,
    client_secret: v('cfg_r1_client_secret') || _MASKED,
  } : null;
  if (ruckus_r1) Object.keys(ruckus_r1).forEach(k => ruckus_r1[k] === undefined && delete ruckus_r1[k]);

  // ── Aruba Central ──────────────────────────────────────────
  const acClientId = v('cfg_ac_client_id');
  const aruba_central = acClientId ? {
    base_url:      'https://apigw-prod2.central.arubanetworks.com',
    customer_id:   v('cfg_ac_customer_id'),
    client_id:     acClientId,
    client_secret: v('cfg_ac_client_secret') || _MASKED,
  } : null;

  // ── ExtremeCloud IQ ────────────────────────────────────────
  const xiqApiKey = v('cfg_xiq_api_key');
  const extreme_iq = xiqApiKey ? {
    base_url: 'https://extremecloudiq.com',
    api_key:  xiqApiKey || _MASKED,
  } : null;

  // ── Server ─────────────────────────────────────────────────
  const originsRaw = v('cfg_srv_origins');
  const allowed_origins = originsRaw
    ? originsRaw.split(',').map(s => s.trim()).filter(Boolean)
    : [];
  const server = {
    host:            v('cfg_srv_host') || '0.0.0.0',
    port:            parseInt(v('cfg_srv_port')) || 8080,
    api_key:         v('cfg_srv_api_key') || _MASKED,
    allowed_origins,
  };

  return {
    switch_credentials,
    cisco_switches: collectSwitches('cisco'),
    aruba_switches: collectSwitches('aruba'),
    fortigate,
    ruckus_r1,
    aruba_central,
    extreme_iq,
    server,
  };
}

// ── Discovery ─────────────────────────────────────────────────
let _discController = null;    // AbortController for the active discovery
let _discDevices    = [];       // devices received in the "done" event

function discUpdateProtocolFields() {
  const proto = document.getElementById('disc_protocol')?.value || 'ssh';
  const showSsh  = proto === 'ssh'  || proto === 'both';
  const showSnmp = proto === 'snmp' || proto === 'both';
  const sshEl  = document.getElementById('disc_ssh_fields');
  const snmpEl = document.getElementById('disc_snmp_fields');
  if (sshEl)  sshEl.style.display  = showSsh  ? '' : 'none';
  if (snmpEl) snmpEl.style.display = showSnmp ? '' : 'none';
}

async function startDiscovery() {
  const seedIp = document.getElementById('disc_seed_ip')?.value.trim();
  if (!seedIp) {
    alert('Enter a seed IP address to start discovery.');
    return;
  }

  // Reset UI
  const progress = document.getElementById('discProgress');
  const results  = document.getElementById('discResults');
  const log      = document.getElementById('discLog');
  const startBtn = document.getElementById('discStartBtn');
  const stopBtn  = document.getElementById('discStopBtn');

  progress.classList.remove('hidden');
  results.classList.add('hidden');
  log.innerHTML = '';
  _discDevices  = [];
  document.getElementById('discProgressLabel').textContent = 'Discovering…';
  startBtn.disabled = true;
  stopBtn.style.display = '';

  // Build request body
  const protocol     = document.getElementById('disc_protocol')?.value || 'ssh';
  const usernameOvr  = document.getElementById('disc_username')?.value.trim();
  const passwordOvr  = document.getElementById('disc_password')?.value.trim();
  const body = {
    seed_ip:   seedIp,
    scope:     document.getElementById('disc_scope')?.value.trim() || '',
    max_depth: parseInt(document.getElementById('disc_depth')?.value) || 5,
    protocol,
    credentials: (usernameOvr && passwordOvr) ? {
      username:    usernameOvr,
      password:    passwordOvr,
      device_type: document.getElementById('disc_device_type')?.value || 'cisco_ios',
      timeout:     15,
    } : {},
    snmp: {
      community: document.getElementById('disc_snmp_community')?.value.trim() || 'public',
      port:      parseInt(document.getElementById('disc_snmp_port')?.value) || 161,
      version:   document.getElementById('disc_snmp_version')?.value || '2c',
    },
  };

  // Use fetch + ReadableStream for SSE (works with API key header that EventSource can't send)
  _discController = new AbortController();
  try {
    const res = await apiFetch('/api/discover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: _discController.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      _discLog('error', '', '', err.detail || 'Request failed', 0);
      startBtn.disabled = false;
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();   // keep incomplete last line
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const evt = JSON.parse(line.slice(6));
            _handleDiscoveryEvent(evt);
          } catch (_) { /* ignore malformed */ }
        }
      }
    }
  } catch(e) {
    if (e.name !== 'AbortError') {
      _discLog('error', seedIp, '', 'Connection lost: ' + e.message, 0);
    }
  } finally {
    startBtn.disabled = false;
    stopBtn.style.display = 'none';
    _discController = null;
  }
}

function stopDiscovery() {
  if (_discController) {
    _discController.abort();
    document.getElementById('discProgressLabel').textContent = 'Stopped.';
  }
}

function _handleDiscoveryEvent(evt) {
  const log = document.getElementById('discLog');
  switch (evt.type) {
    case 'connecting':
      _discLog('connecting', evt.ip, '', 'connecting…', evt.depth);
      break;
    case 'found':
      _discLog('found', evt.ip, evt.hostname, evt.platform || evt.device_type, evt.depth);
      break;
    case 'skip':
      _discLog('skip', evt.ip, evt.hostname, evt.reason, evt.depth);
      break;
    case 'error':
      _discLog('error', evt.ip, '', evt.reason, evt.depth);
      break;
    case 'done':
      _discDevices = evt.devices || [];
      document.getElementById('discProgressLabel').textContent =
        `Done — ${_discDevices.length} device${_discDevices.length !== 1 ? 's' : ''} found`;
      _renderDiscoveryResults(_discDevices);
      break;
  }
  // Auto-scroll log
  if (log) log.scrollTop = log.scrollHeight;
}

function _discLog(type, ip, hostname, meta, depth) {
  const log = document.getElementById('discLog');
  if (!log) return;
  const icons = { connecting: '⟳', found: '✓', skip: '·', error: '✗' };
  const indent = depth > 0 ? `<span style="opacity:.3">${'  '.repeat(Math.min(depth,4))}</span>` : '';
  const row = document.createElement('div');
  row.className = `disc-log-row disc-log-row--${type}`;
  row.innerHTML =
    `${indent}<span class="disc-log-icon">${icons[type] || '·'}</span>` +
    `<span class="disc-log-ip">${esc(ip)}</span>` +
    (hostname ? `<span class="disc-log-host">${esc(hostname)}</span>` : '') +
    (meta     ? `<span class="disc-log-meta">${esc(meta)}</span>` : '');
  log.appendChild(row);
}

function _renderDiscoveryResults(devices) {
  const container = document.getElementById('discDeviceList');
  const section   = document.getElementById('discResults');
  if (!container) return;
  container.innerHTML = '';

  if (!devices.length) {
    section.classList.remove('hidden');
    document.getElementById('discResultsLabel').textContent = 'No new devices found';
    return;
  }

  const seedIp = document.getElementById('disc_seed_ip')?.value.trim();
  devices.forEach((d, i) => {
    const isSeed = d.mgmt_ip === seedIp;
    const row = document.createElement('label');
    row.className = 'disc-device-row' + (isSeed ? ' disc-device-row--seed' : '');
    row.innerHTML =
      `<input type="checkbox" class="disc-check" data-idx="${i}" ${isSeed ? '' : 'checked'}>` +
      `<span class="disc-device-hostname">${esc(d.hostname || d.mgmt_ip)}</span>` +
      `<span class="disc-device-ip">${esc(d.mgmt_ip)}</span>` +
      `<span class="disc-device-type">${esc(d.device_type || 'cisco_ios')}</span>`;
    container.appendChild(row);
  });

  document.getElementById('discResultsLabel').textContent =
    `${devices.length} device${devices.length !== 1 ? 's' : ''} found — select to add`;
  section.classList.remove('hidden');
}

function discToggleAll(checked) {
  document.querySelectorAll('.disc-check').forEach(cb => cb.checked = checked);
}

function addDiscoveredDevices() {
  const selected = Array.from(document.querySelectorAll('.disc-check:checked'))
    .map(cb => _discDevices[parseInt(cb.dataset.idx)])
    .filter(Boolean);

  if (!selected.length) {
    alert('No devices selected.');
    return;
  }

  // Determine which list to add to based on device_type
  selected.forEach(d => {
    const isAruba = (d.device_type || '').startsWith('aruba');
    const listId  = isAruba ? 'aruba_switches_list' : 'cisco_switches_list';
    const type    = isAruba ? 'aruba' : 'cisco';

    // Don't add duplicates (check by host)
    const existing = Array.from(
      document.querySelectorAll(`#${listId} .sw-host`)
    ).map(el => el.value.trim());
    if (existing.includes(d.mgmt_ip)) return;

    _appendSwitchRow(type, {
      name:        d.hostname || d.mgmt_ip,
      host:        d.mgmt_ip,
      device_type: d.device_type || 'cisco_ios',
      os_type:     d.device_type || 'aruba_os',
    });
  });

  // Show feedback
  const msg = document.getElementById('settingsSaveMsg');
  msg.textContent = `✓ Added ${selected.length} device${selected.length !== 1 ? 's' : ''} to inventory. Save to persist.`;
  msg.className = 'settings-save-msg ok';
  msg.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
    _lastResult = data;
    _lastQuery  = query;
    _saveToHistory(query, data);
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
  // Update print-only header
  const _ph = document.getElementById('printHeaderMeta');
  if (_ph) {
    const _mac = data.resolved_mac ? `MAC: ${data.resolved_mac}` : '';
    const _ip  = data.resolved_ip  ? `IP: ${data.resolved_ip}`   : '';
    _ph.textContent = [_lastQuery, _mac, _ip, new Date().toLocaleString()].filter(Boolean).join('  ·  ');
  }
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

  // Vendor path chips
  const vendorsEl = document.getElementById('summaryVendors');
  if (vendorsEl) {
    const chips = _vendorPathFromHops(data.path || []);
    vendorsEl.innerHTML = chips.map((c, i) =>
      (i > 0 ? '<span class="summary-vendor-arrow">›</span>' : '') +
      `<span class="summary-vendor-chip" style="color:${c.color}">${esc(c.label)}</span>`
    ).join('');
  }

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

function _vendorPathFromHops(path) {
  const chips = [];
  let lastLabel = null;
  for (const hop of path) {
    const meta = VENDOR_PATH_META[hop.device_type];
    if (!meta) continue;                      // skip client / unknown
    if (meta.label === lastLabel) continue;   // deduplicate consecutive same-vendor hops
    chips.push(meta);
    lastLabel = meta.label;
  }
  return chips;
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
      <span class="issue-sev ${issue.severity}">${esc(issue.severity)}</span>
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
          ${s.mtu ? `MTU: ${esc(String(s.mtu))} bytes.` : ''}
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
        <span class="issue-sev ${issue.severity}">${esc(issue.severity)}</span>
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

// ── CSV export ────────────────────────────────────────────────
function downloadCsv() {
  if (!_lastResult) return;
  const rows = [];

  // Header
  rows.push(['Hop', 'Device Name', 'Type', 'IP', 'Vendor', 'Model', 'Version',
    'VLAN', 'Ingress Port', 'Egress Port', 'Reachable',
    'Issues', 'Tests Passed', 'Tests Failed', 'Tests Warning']);

  // One row per hop
  (_lastResult.path || []).forEach((hop, i) => {
    const issues  = (hop.issues || []).map(is => `${is.severity}: ${is.message}`).join('; ');
    const tests   = hop.tests || [];
    const passed  = tests.filter(t => t.status === 'pass').length;
    const failed  = tests.filter(t => t.status === 'fail').length;
    const warning = tests.filter(t => t.status === 'warning').length;
    rows.push([
      i + 1,
      hop.device_name      || '',
      hop.device_type      || '',
      hop.device_ip        || '',
      hop.vendor           || '',
      hop.model            || '',
      hop.software_version || '',
      hop.vlan             || '',
      hop.ingress_port     || '',
      hop.egress_port      || '',
      hop.reachable != null ? (hop.reachable ? 'Yes' : 'No') : '',
      issues,
      passed,
      failed,
      warning,
    ]);
  });

  // All issues appendix
  const allIssues = _lastResult.all_issues || [];
  if (allIssues.length) {
    rows.push([]);
    rows.push(['--- ALL ISSUES ---']);
    rows.push(['Severity', 'Device', 'Message', 'Detail']);
    allIssues.forEach(is => rows.push([
      is.severity || '', is.device || '', is.message || '', is.detail || '',
    ]));
  }

  // Serialise — RFC 4180 CSV with UTF-8 BOM for Excel
  const csv = rows.map(row =>
    row.map(cell => {
      const s = String(cell ?? '');
      return (s.includes(',') || s.includes('\n') || s.includes('"'))
        ? '"' + s.replace(/"/g, '""') + '"' : s;
    }).join(',')
  ).join('\r\n');

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const ts   = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '');
  const safe = _lastQuery.replace(/[^a-zA-Z0-9._:-]/g, '_').slice(0, 40);
  a.href     = url;
  a.download = `netinspect_${safe}_${ts}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Trace history (localStorage) ─────────────────────────────
const _HISTORY_KEY = 'netinspect_history';
const _HISTORY_MAX = 20;

function _saveToHistory(query, result) {
  try {
    const entries = _loadHistoryEntries();
    const crits = (result.all_issues || []).filter(i => i.severity === 'critical').length;
    const warns = (result.all_issues || []).filter(i => i.severity === 'warning').length;
    entries.unshift({
      id:           Date.now(),
      query,
      timestamp:    new Date().toISOString(),
      resolved_mac: result.resolved_mac || '',
      resolved_ip:  result.resolved_ip  || '',
      status:       result.status || 'ok',
      hop_count:    (result.path || []).length,
      crit_count:   crits,
      warn_count:   warns,
      result,
    });
    if (entries.length > _HISTORY_MAX) entries.length = _HISTORY_MAX;
    localStorage.setItem(_HISTORY_KEY, JSON.stringify(entries));
    _renderHistoryPanel(entries);
  } catch (_) { /* storage full or disabled — fail silently */ }
}

function _loadHistoryEntries() {
  try { return JSON.parse(localStorage.getItem(_HISTORY_KEY) || '[]'); }
  catch (_) { return []; }
}

function _renderHistoryPanel(entries) {
  const panel = document.getElementById('historyPanel');
  const list  = document.getElementById('historyList');
  const count = document.getElementById('historyCount');
  if (!panel) return;
  if (!entries.length) { panel.style.display = 'none'; return; }

  panel.style.display = '';
  if (count) count.textContent = entries.length;
  if (!list) return;
  list.innerHTML = '';

  entries.forEach(e => {
    const icon = e.status === 'not_found' ? '🔍' : e.crit_count ? '🔴' : e.warn_count ? '⚠️' : '✅';
    const ts   = new Date(e.timestamp).toLocaleString(undefined,
      { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const meta = [ts, `${e.hop_count} hop${e.hop_count !== 1 ? 's' : ''}`,
      e.resolved_ip || '', e.resolved_mac || ''].filter(Boolean).join('  ·  ');
    const row = document.createElement('div');
    row.className = 'history-row';
    row.innerHTML =
      `<span class="history-row-icon">${icon}</span>` +
      `<div class="history-row-body">` +
        `<div class="history-row-query">${esc(e.query)}</div>` +
        `<div class="history-row-meta">${esc(meta)}</div>` +
      `</div>` +
      `<button class="history-row-load" title="Reload this trace">↩ Load</button>`;
    row.querySelector('.history-row-load')
      .addEventListener('click', () => loadHistoricTrace(e.id));
    list.appendChild(row);
  });
}

function toggleHistory() {
  const list  = document.getElementById('historyList');
  const caret = document.getElementById('historyCaret');
  if (!list) return;
  const open = list.style.display === 'none';
  list.style.display = open ? '' : 'none';
  if (caret) caret.style.transform = open ? 'rotate(90deg)' : '';
}

function loadHistoricTrace(id) {
  const entry = _loadHistoryEntries().find(e => e.id === id);
  if (!entry) return;
  _lastResult = entry.result;
  _lastQuery  = entry.query;
  document.getElementById('searchInput').value = entry.query;
  renderResults(entry.result);
  setState('results');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function clearHistory(event) {
  event.stopPropagation();   // don't trigger toggleHistory
  localStorage.removeItem(_HISTORY_KEY);
  _renderHistoryPanel([]);
}
