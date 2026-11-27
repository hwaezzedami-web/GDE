#!/usr/bin/env python3
"""Build assets/index.html for the Android app from the shared page ../app/wallet.html.

The interface is the same; this swaps the claude.ai runtime for on-phone storage:
- data lives in one JSON file through the AndroidWallet bridge (localStorage when opened in a browser),
- Excel export uses the bundled xlsx.full.min.js and the phone's "save file" screen,
- Settings gets Backup / Restore, and the claude.ai sharing notes are replaced.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = (HERE.parent / "app" / "wallet.html").read_text(encoding="utf8")


def rep(old: str, new: str) -> None:
    global src
    count = src.count(old)
    assert count == 1, f"expected 1 match, found {count}: {old[:80]!r}"
    src = src.replace(old, new)


# 1. no web fonts (works offline), no claude.ai-only meta
rep('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
rep('<link rel="preconnect" href="https://fonts.googleapis.com">\n', "")
rep('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n', "")
rep('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600&family=Readex+Pro:wght@400;600;700&display=swap">\n', "")
rep('--font-display: "Readex Pro", "IBM Plex Sans Arabic", system-ui,', '--font-display: "Readex Pro", "IBM Plex Sans Arabic", Roboto, "Noto Sans Arabic", system-ui,')

# 2. new texts
rep('    both: "Both", da: "DA",\n', '''    both: "Both", da: "DA",
    backupT: "Backup", backupB: "Save backup file", restoreB: "Restore from backup", restoreYes: "Yes, replace my data",
    backupNote: "Your data is saved on this phone only. Save a backup file every month and keep it in Google Drive or send it to yourself. If you change phone or reinstall the app, restore it here.",
    restoreConfirm: "Replace all the data on this phone with this backup ({n} entries, saved {d})?", restoreBad: "This file is not a wallet backup.", restored: "Backup restored",
    phoneT: "On this phone", phoneNote: "Works without internet and without a laptop. Bouchra can install the same app on her phone; each phone keeps its own data. To copy your data to another phone, save a backup here and restore it there.",
    version: "Version", fileSaved: "File saved", notSaved: "File not saved",
''')
rep('    both: "مشترك", da: "دج",\n', '''    both: "مشترك", da: "دج",
    backupT: "نسخة احتياطية", backupB: "حفظ نسخة احتياطية", restoreB: "استرجاع نسخة احتياطية", restoreYes: "نعم، استبدل بياناتي",
    backupNote: "بياناتك محفوظة في هذا الهاتف فقط. احفظ نسخة احتياطية كل شهر وضعها في Google Drive أو أرسلها لنفسك. إذا غيرت الهاتف أو أعدت تثبيت التطبيق، استرجعها من هنا.",
    restoreConfirm: "استبدال كل البيانات في هذا الهاتف بهذه النسخة ({n} عنصر، محفوظة في {d})؟", restoreBad: "هذا الملف ليس نسخة احتياطية للمحفظة.", restored: "تم الاسترجاع",
    phoneT: "على هذا الهاتف", phoneNote: "يعمل بدون إنترنت وبدون حاسوب. يمكن لبشرى تثبيت نفس التطبيق على هاتفها؛ كل هاتف يحفظ بياناته. لنقل بياناتك إلى هاتف آخر، احفظ نسخة هنا واسترجعها هناك.",
    version: "الإصدار", fileSaved: "تم حفظ الملف", notSaved: "لم يُحفظ الملف",
''')

# 3. settings screen: backup / restore instead of claude.ai sharing notes
rep('''  <section class="card"><h2>${esc(t("shareT"))}</h2><p class="small">${esc(t("shareNote"))}</p></section>
  <section class="card"><h2>${esc(t("homeT"))}</h2><p class="small">${esc(t("homeNote"))}</p></section>`;''',
    '''  <section class="card"><h2>${esc(t("backupT"))}</h2><p class="small">${esc(t("backupNote"))}</p>
    <div class="actions"><button class="btn" type="button" data-act="backup">${ic("download")}${esc(t("backupB"))}</button>
    <button class="btn ghost" type="button" data-act="restore">${esc(t("restoreB"))}</button></div>
    <input type="file" id="restoreFile" accept=".json,application/json,text/plain" hidden></section>
  <section class="card"><h2>${esc(t("phoneT"))}</h2><p class="small">${esc(t("phoneNote"))}</p><p class="small muted">${esc(t("version"))} 1.4</p></section>`;''')

# 4. Excel export with the bundled library and the phone's save screen
rep('''  const dl = window.claude && window.claude.use ? await window.claude.use("downloads") : null;
  if (!dl) return toast(t("exportNA"));
  toast(t("exporting"));
  try { await loadScript("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"); }''',
    '''  toast(t("exporting"));
  try { await loadScript("xlsx.full.min.js"); }''')
rep('''  const buf = X.write(wb, { bookType: "xlsx", type: "array" });
  try { await dl.save({ filename: `Wallet_${todayStr()}.xlsx`, data: new Uint8Array(buf) }); toast(t("saved2")); }
  catch (e) { if (e && e.code !== "declined") toast(e.code === "host_unavailable" ? t("exportNA") : t("errSave", { m: e.code || "?" })); }''',
    '''  saveOut(`Wallet_${todayStr()}.xlsx`, X.write(wb, { bookType: "xlsx", type: "base64" }), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");''')

# 5. restore confirmation sheet
rep("  body.innerHTML = html;\n", '''  if (sh.type === "restore") {
    html = sheetHead(t("restoreB")) + `<p>${esc(t("restoreConfirm", { n: sh.count, d: sh.when }))}</p>
      <div class="actions"><button class="btn danger" type="button" data-act="restoreYes">${esc(t("restoreYes"))}</button>
      <button class="btn ghost" type="button" data-act="close">${esc(t("cancel"))}</button></div>`;
  }
  body.innerHTML = html;
''')

# 6. extra buttons
rep('''  else if (a === "export") exportXlsx();''', '''  else if (a === "export") exportXlsx();
  else if (a === "backup") backupNow();
  else if (a === "restore") { const f = document.getElementById("restoreFile"); if (f) { f.value = ""; f.click(); } }
  else if (a === "restoreYes") doRestore();''')

# 7. on-phone storage that speaks the same small API the page already uses
rep("/* ------------------------------------------------------------------ start */", r'''/* ------------------------------------------------------------------ on-phone storage */
const LocalDB = (() => {
  const KEY = "wallet.data.v1", bridge = window.AndroidWallet;
  let state = { colls: {}, config: null };
  const subs = {};
  try {
    const raw = bridge ? bridge.load() : localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && parsed.colls) state = { colls: parsed.colls, config: parsed.config || null };
  } catch (e) { /* start empty */ }
  function persist() {
    const raw = JSON.stringify({ app: "aboubakr-wallet", version: 1, colls: state.colls, config: state.config });
    let ok = false;
    try { ok = bridge ? bridge.save(raw) : (localStorage.setItem(KEY, raw), true); } catch (e) { ok = false; }
    if (!ok) throw { code: "storage", message: "the phone refused to save" };
  }
  const emit = (k) => (subs[k] || []).slice().forEach((fn) => fn());
  const listen = (k, fn) => { (subs[k] = subs[k] || []).push(fn); setTimeout(fn, 0); return () => { subs[k] = (subs[k] || []).filter((f) => f !== fn); }; };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const snap = (c) => { const o = state.colls[c] || {}; return { docs: Object.keys(o).map((id) => ({ id, data: () => o[id] })), metadata: { fromCache: false, hasPendingWrites: false } }; };
  return {
    collection(c) {
      return {
        onSnapshot(next) { return listen(c, () => next(snap(c))); },
        doc(id) {
          const docId = id || newId();
          return {
            async set(obj) { const all = (state.colls[c] = state.colls[c] || {}); const before = all[docId]; all[docId] = clone(obj);
              try { persist(); } catch (e) { if (before === undefined) delete all[docId]; else all[docId] = before; throw e; } emit(c); },
            async delete() { const all = state.colls[c] || {}; const before = all[docId]; delete all[docId];
              try { persist(); } catch (e) { if (before !== undefined) all[docId] = before; throw e; } emit(c); },
          };
        },
      };
    },
    doc() {
      return {
        onSnapshot(next) { return listen("config", () => next({ exists: !!state.config, data: () => state.config || undefined })); },
        async set(obj) { const before = state.config; state.config = clone(obj); try { persist(); } catch (e) { state.config = before; throw e; } emit("config"); },
      };
    },
    exportAll() { return { app: "aboubakr-wallet", version: 1, saved: new Date().toISOString(), colls: clone(state.colls), config: clone(state.config) }; },
    importAll(obj) { const before = state; state = { colls: clone(obj.colls), config: obj.config ? clone(obj.config) : null };
      try { persist(); } catch (e) { state = before; throw e; } Object.keys(subs).forEach(emit); },
  };
})();
function b64utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
function saveOut(name, b64, mime) {
  if (window.AndroidWallet && window.AndroidWallet.saveFile) { window.AndroidWallet.saveFile(name, b64, mime); return; }
  const a = document.createElement("a");
  a.href = "data:" + mime + ";base64," + b64; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
}
window.walletSaved = (ok) => toast(ok ? t("fileSaved") : t("notSaved"));
function backupNow() { saveOut(`Wallet_backup_${todayStr()}.json`, b64utf8(JSON.stringify(LocalDB.exportAll())), "application/json"); }
function readRestore(file) {
  if (!file) return;
  const fr = new FileReader();
  fr.onload = () => {
    let obj = null;
    try { obj = JSON.parse(String(fr.result)); } catch (e) { obj = null; }
    if (!obj || obj.app !== "aboubakr-wallet" || !obj.colls || typeof obj.colls !== "object") return toast(t("restoreBad"));
    const count = Object.values(obj.colls).reduce((s, c) => s + (c && typeof c === "object" ? Object.keys(c).length : 0), 0);
    S.sheet = { type: "restore", data: obj, count, when: obj.saved ? dmy(String(obj.saved).slice(0, 10)) : "?" };
    renderSheet();
  };
  fr.onerror = () => toast(t("restoreBad"));
  fr.readAsText(file);
}
function doRestore() {
  const sh = S.sheet; if (!sh || sh.type !== "restore") return;
  try { LocalDB.importAll(sh.data); S.sheet = null; renderSheet(); toast(t("restored")); }
  catch (e) { toast(t("errSave", { m: (e && e.message) || "?" })); }
}
document.addEventListener("change", (e) => { if (e.target && e.target.id === "restoreFile") readRestore(e.target.files && e.target.files[0]); });
function applyTheme(dark) {
  const b = window.AndroidWallet;
  if (dark === undefined && b && b.isDark) { try { dark = b.isDark(); } catch (e) { dark = undefined; } }
  if (dark === undefined) document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}
window.walletTheme = (dark) => applyTheme(!!dark);
window.walletBack = () => {
  if (S.sheet) { closeSheet(); return true; }
  if (S.route !== "home") { go("home"); return true; }
  return false;
};

/* ------------------------------------------------------------------ start */''')
rep('''  const C = window.claude;
  const [db, user] = C && C.use ? await Promise.all([C.use("db"), C.use("user")]) : [null, null];
  if (!db) { S.dbState = "none"; render(); return; }
  S.db = db;
  if (user) { try { const w = await user.can("data.write"); S.canWrite = w === null || w === undefined ? null : !!w; } catch (e) { /* keep inputs */ } }''',
    '''  applyTheme();
  const db = LocalDB;
  S.db = db; S.canWrite = true;''')

# 8. a full document (the claude.ai viewer adds this skeleton itself)
page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}'
        'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>\n'
        + src + '\n</body></html>\n')
(HERE / "assets" / "index.html").write_text(page, encoding="utf8")
print("index.html ok", len(page), "bytes")
