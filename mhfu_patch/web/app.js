'use strict';

const TOKEN = window.PATCHER_TOKEN || '';
const $ = (id) => document.getElementById(id);

const S = { info: null, es: null, job: null, home: '~', browse: { path: null, parent: null } };

/* ---------------- util ---------------- */
const show = (el) => el.removeAttribute('hidden');
const hide = (el) => el.setAttribute('hidden', '');
const mb = (n) => ((n || 0) / 1e6).toFixed(1) + ' MB';
const short = (s, n = 16) => (s || '').slice(0, n) + '…';
const dirname = (p) => p.includes('/') ? p.slice(0, p.lastIndexOf('/')) || '/' : '.';
const base = (p) => p.split('/').pop();

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function kv(key, value, opts = {}) {
  const box = el('div', 'kv');
  box.appendChild(el('div', 'k', key));
  const v = el('div', 'v' + (opts.mono ? ' mono' : '') + (opts.tone ? ' ' + opts.tone : ''), value);
  if (opts.title) v.title = opts.title;
  box.appendChild(v);
  return box;
}

function step(n) {
  for (let i = 1; i <= 3; i++) {
    const node = $('step' + i);
    node.classList.toggle('active', i === n);
    node.classList.toggle('done', i < n);
  }
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) { button.dataset.label = button.textContent; button.textContent = label || '…'; }
  else if (button.dataset.label) { button.textContent = button.dataset.label; }
  button.disabled = busy;
}

function showErr(id, message) {
  const node = $(id);
  node.textContent = message;
  show(node);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Patch-Token': TOKEN },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!data) throw new Error('Server tidak memberi jawaban yang valid.');
  if (!res.ok || data.ok === false) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

/* ---------------- boot ---------------- */
async function boot() {
  $('browseBtn').addEventListener('click', () => openBrowse(S.info ? dirname(S.info.ipa) : (S.home || '~')));
  $('inspectBtn').addEventListener('click', inspect);
  $('ipaPath').addEventListener('keydown', (e) => { if (e.key === 'Enter') inspect(); });
  $('dryBtn').addEventListener('click', () => start(true));
  $('patchBtn').addEventListener('click', () => start(false));
  $('cancelBtn').addEventListener('click', cancel);
  $('revealBtn').addEventListener('click', reveal);
  $('againBtn').addEventListener('click', reset);
  $('closeBtn').addEventListener('click', closeBrowse);
  $('upBtn').addEventListener('click', () => { if (S.browse.parent) loadDir(S.browse.parent); });
  $('modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeBrowse(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeBrowse(); });
  ['outPath', 'version'].forEach((id) => $(id).addEventListener('keydown', (e) => {
    if (e.key === 'Enter') start(false);
  }));

  try {
    const hello = await api('/api/hello');
    S.home = hello.home || '~';
    $('setBadge').textContent = (hello.patch_sets[0] || {}).title || hello.default || '';
    $('setBadge').title = hello.default || '';
    const quick = $('quick');
    [['Beranda', hello.home], ['Unduhan', (hello.home || '') + '/Downloads']].forEach(([label, path]) => {
      const b = el('button', 'btn ghost', label);
      b.addEventListener('click', () => { $('ipaPath').value = ''; openBrowse(path); });
      quick.appendChild(b);
      quick.append(' ');
    });
  } catch (e) {
    showErr('pickErr', 'Gagal menghubungi server: ' + e.message);
  }
}

/* ---------------- browse ---------------- */
function openBrowse(path) {
  show($('modal'));
  loadDir(path || '~');
}

function closeBrowse() { hide($('modal')); }

async function loadDir(path) {
  const listing = $('listing');
  listing.replaceChildren(el('div', 'entry empty', 'memuat…'));
  try {
    const data = await api('/api/list', { path });
    S.browse.path = data.path;
    S.browse.parent = data.parent;
    $('browsePath').textContent = data.path;
    $('browsePath').title = data.path;
    $('upBtn').disabled = !data.parent;
    listing.replaceChildren();
    data.dirs.forEach((name) => {
      const row = el('div', 'entry');
      row.append(el('span', 'ico', '▸'), el('span', '', name));
      row.addEventListener('click', () => loadDir(data.path.replace(/\/$/, '') + '/' + name));
      listing.appendChild(row);
    });
    data.files.forEach((file) => {
      const row = el('div', 'entry file');
      row.append(el('span', 'ico', '◆'), el('span', '', file.name));
      row.append(el('span', 'size', mb(file.size)));
      row.addEventListener('click', () => {
        $('ipaPath').value = data.path.replace(/\/$/, '') + '/' + file.name;
        closeBrowse();
        inspect();
      });
      listing.appendChild(row);
    });
    if (!data.dirs.length && !data.files.length) {
      listing.appendChild(el('div', 'entry empty', 'tidak ada subfolder atau file .ipa'));
    }
  } catch (e) {
    listing.replaceChildren(el('div', 'entry empty', e.message));
  }
}

/* ---------------- inspect ---------------- */
async function inspect() {
  const ipa = $('ipaPath').value.trim();
  hide($('pickErr'));
  if (!ipa) return showErr('pickErr', 'Isi path IPA terlebih dahulu.');
  setBusy($('inspectBtn'), true, 'Memeriksa…');
  try {
    const { info } = await api('/api/inspect', { ipa });
    S.info = info;
    renderInfo(info);
    step(2);
  } catch (e) {
    S.info = null;
    hide($('cardInfo'));
    hide($('cardPatch'));
    showErr('pickErr', e.message);
    step(1);
  } finally {
    setBusy($('inspectBtn'), false);
  }
}

function renderInfo(info) {
  const grid = $('infoGrid');
  grid.replaceChildren(
    kv('Aplikasi', info.app_name + ' — ' + (info.bundle_id || '?')),
    kv('Versi di IPA', info.info_version || '?'),
    kv('Biner', info.exe_kind + ' · ' + info.slices.length + ' slice'),
    kv('Slice arm64', short(info.arm64_sha256, 20) + ' · ' + mb(info.arm64_size), { mono: true }),
    kv('Member', String(info.members) + ' file'),
    kv('Patch set', info.patch_set || '—', { title: info.patch_title || '' }),
    kv('Langkah biner', info.steps_total ? (info.steps_pending + ' belum / ' + info.steps_total + ' total') : '—'),
    kv('Paket', info.supported ? (info.remove_pending.length + ' dihapus · ' + info.add_pending.length + ' ditambah') : '—'),
    kv('Status',
      info.supported ? (info.steps_pending ? 'Siap dipatch' : 'Sudah dipatch') : 'Tidak didukung',
      { tone: info.supported ? (info.steps_pending ? 'ok' : 'warm') : 'bad' }),
  );
  show($('cardInfo'));

  const warn = $('infoWarn');
  const notes = [];
  if (!info.supported) notes.push(info.reason || 'IPA tidak didukung.');
  if (info.supported && !info.steps_pending && !info.remove_pending.length && !info.add_pending.length) {
    notes.push('Biner sudah berisi patch lengkap. Untuk membangun ulang, ganti nomor versi.');
  }
  if (info.free_space !== null && info.free_space < info.size + 33.5e6) {
    notes.push('Ruang disk di folder tujuan kurang (perlu ± ' + mb(info.size + 33.5e6) + ').');
  }
  if (notes.length) { warn.textContent = notes.join(' '); show(warn); } else hide(warn);

  const chips = $('featChips');
  chips.replaceChildren();
  (info.features || []).forEach((f) => {
    const chip = el('span', 'chip');
    chip.append(el('b', '', f.title || f.id));
    chips.appendChild(chip);
  });
  if ((info.features || []).length) show($('featWrap')); else hide($('featWrap'));

  if (!info.supported) {
    hide($('cardPatch'));
    return;
  }
  $('fatWrap').hidden = info.exe_kind !== 'fat';
  $('keepFat').checked = false;

  const version = suggestVersion(info);
  $('version').value = version;
  $('outPath').value = dirname(info.ipa).replace(/\/$/, '') + '/MHFU_patched_' + version + '.ipa';
  show($('cardPatch'));
  hide($('cardDone'));
  hide($('cardProg'));
}

function suggestVersion(info) {
  if (info.match === 'result' || (!info.steps_pending && !info.remove_pending.length && !info.add_pending.length)) {
    const parts = String(info.info_version || '1.00.194').split('.');
    const last = parseInt(parts[parts.length - 1], 10);
    if (!Number.isNaN(last)) parts[parts.length - 1] = String(last + 1);
    return parts.join('.');
  }
  return info.patch_version || '1.00.194';
}

/* ---------------- patch ---------------- */
async function start(dry) {
  if (!S.info) return;
  const ipa = $('ipaPath').value.trim();
  const out = $('outPath').value.trim();
  const version = $('version').value.trim();
  if (!out) return showErr('pickErr', 'Isi path file hasil.');
  hide($('pickErr'));
  hide($('cardDone'));

  const title = $('progTitle');
  title.textContent = dry ? 'Dry run…' : 'Memproses…';
  $('progFill').style.width = '0%';
  $('progPct').textContent = '0%';
  $('progPhase').textContent = 'menyiapkan';
  $('progLog').textContent = '';
  show($('cardProg'));
  $('cardProg').scrollIntoView({ behavior: 'smooth', block: 'start' });
  show($('cancelBtn'));
  $('dryBtn').disabled = true;
  $('patchBtn').disabled = true;
  step(3);

  try {
    const { job } = await api('/api/start', {
      ipa, out, version,
      keep_fat: $('keepFat').checked,
      dry_run: !!dry,
      force: false,
    });
    S.job = job.id;
    watch(job.id, dry);
  } catch (e) {
    $('progTitle').textContent = 'Gagal';
    $('progPhase').textContent = e.message;
    $('progLog').textContent = e.message;
    $('dryBtn').disabled = false;
    $('patchBtn').disabled = false;
    hide($('cancelBtn'));
  }
}

function watch(id, dry) {
  if (S.es) S.es.close();
  const es = new EventSource('/api/job/' + id + '/events?token=' + encodeURIComponent(TOKEN));
  S.es = es;
  let lastPct = -10;
  es.onmessage = (event) => {
    let data = null;
    try { data = JSON.parse(event.data); } catch (e) { return; }
    if (data.done) {
      es.close();
      S.es = null;
      finish(data.job, dry);
      return;
    }
    const pct = data.pct || 0;
    $('progFill').style.width = Math.max(0, Math.min(100, pct)) + '%';
    $('progPct').textContent = pct + '%';
    $('progPhase').textContent = (data.phase || '') + (data.detail ? ' — ' + data.detail : '');
    if (pct - lastPct >= 5) {
      lastPct = pct;
      const log = $('progLog');
      log.textContent += '[' + String(pct).padStart(3, ' ') + '%] ' + (data.phase || '') +
        (data.detail ? ' — ' + data.detail : '') + '\n';
      log.scrollTop = log.scrollHeight;
    }
  };
  es.onerror = () => { /* server menutup koneksi setelah selesai */ };
}

function finish(snap, dry) {
  hide($('cancelBtn'));
  $('dryBtn').disabled = false;
  $('patchBtn').disabled = false;
  if (!snap) return;

  if (snap.state === 'error') {
    $('progTitle').textContent = 'Gagal';
    $('progPhase').textContent = snap.error || 'kesalahan tidak diketahui';
    $('progLog').textContent += '\n✗ ' + (snap.error || '') + '\n';
    return;
  }
  if (snap.state === 'cancelled') {
    $('progTitle').textContent = 'Dibatalkan';
    $('progPhase').textContent = 'tidak ada file yang ditulis';
    return;
  }

  const r = snap.result || {};
  S.out = r.out || null;
  hide($('cardProg'));
  const grid = $('doneGrid');
  grid.replaceChildren();
  if (dry) {
    $('cardDone').querySelector('h2').textContent = '✓ Dry run selesai';
    grid.append(
      kv('Rencana versi', (r.old_version || '?') + ' → ' + r.version),
      kv('Langkah biner', (r.applied || []).length + ' diterapkan · ' + (r.skipped || []).length + ' dilewati'),
      kv('Paket', (r.removed || []).length + ' dihapus · ' + (r.added || []).length + ' ditambah'),
      kv('Member hasil', String(r.members || '?')),
      kv('Durasi', (r.duration || 0) + ' s'),
    );
    show($('cardDone'));
    $('revealBtn').disabled = true;
    return;
  }

  $('cardDone').querySelector('h2').textContent = '✓ Patch selesai';
  $('revealBtn').disabled = false;
  grid.append(
    kv('File hasil', r.out, { mono: true, title: r.out }),
    kv('Ukuran', mb(r.size)),
    kv('Member', String(r.members)),
    kv('Versi', (r.old_version || '?') + ' → ' + r.version, { tone: 'ok' }),
    kv('Biner', r.exe_kind_out + ' · sha ' + short(r.slice_sha256, 16), { mono: true, tone: 'ok' }),
    kv('Langkah', (r.applied || []).length + ' diterapkan · ' + (r.skipped || []).length + ' dilewati'),
    kv('Paket', (r.removed || []).length + ' dihapus · ' + (r.added || []).length + ' ditambah'),
    kv('Durasi', (r.duration || 0) + ' s'),
    kv('SHA256 IPA', r.output_sha256 || '—', { mono: true, title: r.output_sha256 || '' }),
  );
  show($('cardDone'));
  $('cardDone').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function cancel() {
  try { await api('/api/cancel', { job: S.job }); } catch (e) { /* abaikan */ }
  $('progPhase').textContent = 'membatalkan…';
}

async function reveal() {
  if (!S.out) return;
  try { await api('/api/reveal', { path: S.out }); } catch (e) { alert(e.message); }
}

function reset() {
  S.info = null;
  if (S.es) { S.es.close(); S.es = null; }
  hide($('cardInfo'));
  hide($('cardPatch'));
  hide($('cardProg'));
  hide($('cardDone'));
  hide($('pickErr'));
  $('ipaPath').value = '';
  $('ipaPath').focus();
  step(1);
}

boot();
