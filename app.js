const $ = (s, e = document) => e.querySelector(s), app = $('#app');
const P = new URLSearchParams(location.search);
const rp = n => 'Rp' + Number(n).toLocaleString('id-ID');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const base = location.origin + location.pathname;
const cafes = () => db.collection('cafes');
let first = true;
auth.onAuthStateChanged(() => { if (first) { first = false; route(); } });

function route() {
  if (P.has('r')) return redirect(P.get('r'));
  if (P.has('admin')) return admin();
  if (P.has('c')) return menu(P.get('c'));
  app.innerHTML = '<h1>Cafeee</h1><p>Scan tag di meja untuk melihat menu.</p>';
}

async function redirect(slug) {
  const d = await cafes().doc(slug).get(), u = d.exists && d.data().reviewUrl;
  /^https?:\/\//.test(u || '') ? location.replace(u) : app.innerHTML = '<p class="empty">Link tidak ditemukan.</p>';
}

function login(ok) {
  const m = $('#modal'); m.hidden = false;
  m.innerHTML = `<div class="card"><h3>Masuk</h3><input id="em" type="email" placeholder="Email"><input id="pw" type="password" placeholder="Kata sandi"><p id="err" class="err"></p><button id="in" class="btn">Masuk</button><button id="up" class="ghost">Daftar akun baru</button><button id="x" class="ghost">Tutup</button></div>`;
  const go = fn => async () => { try { await fn($('#em').value.trim(), $('#pw').value); m.hidden = true; ok(); } catch (e) { $('#err').textContent = 'Gagal: ' + e.message; } };
  $('#in').onclick = go((e, p) => auth.signInWithEmailAndPassword(e, p));
  $('#up').onclick = go((e, p) => auth.createUserWithEmailAndPassword(e, p));
  $('#x').onclick = () => m.hidden = true;
}

const menuHTML = c => {
  const g = {};
  (c.menu || []).forEach(i => (g[i.cat || 'Menu'] ??= []).push(i));
  return Object.entries(g).map(([k, v]) => `<h2>${esc(k)}</h2>` + v.map(i =>
    `<div class="row" ${i.on === false ? 'style="opacity:.45"' : ''}><span>${esc(i.name)}${i.on === false ? ' (habis)' : ''}</span><i></i><b>${rp(i.price)}</b></div>`).join('')).join('')
    || '<p class="empty">Menu belum diisi.</p>';
};

async function menu(slug) {
  const d = await cafes().doc(slug).get();
  if (!d.exists || d.data().active === false) return app.innerHTML = '<p class="empty">Cafe tidak ditemukan.</p>';
  const c = d.data();
  app.innerHTML = `<header class="top"><h1>${esc(c.name)}</h1>${c.plan === 'pro' ? '<button id="lock" aria-label="Masuk dashboard toko">🔒</button>' : ''}</header>
  <div>${menuHTML(c)}</div>${/^https?:\/\//.test(c.reviewUrl || '') ? `<a class="btn" href="${esc(c.reviewUrl)}">Beri ulasan di Google</a>` : ''}`;
  $('#lock')?.addEventListener('click', () => {
    const open = () => auth.currentUser?.email === c.ownerEmail ? dash(slug, c) : alert('Akun ini bukan pemilik toko.');
    auth.currentUser ? open() : login(open);
  });
}

function dash(slug, c) {
  let m = c.menu || [], cart = {};
  const save = () => cafes().doc(slug).update({ menu: m, updatedAt: firebase.firestore.FieldValue.serverTimestamp() });
  const draw = () => {
    app.innerHTML = `<header class="top"><h1>${esc(c.name)}</h1><button id="out" class="ghost">Keluar</button></header>
    <form id="add" class="add"><input name="name" placeholder="Nama menu" required><input name="cat" placeholder="Kategori"><input name="price" type="number" min="0" placeholder="Harga" required><button class="btn" style="margin:0">Tambah</button></form>
    <div>${m.map((i, n) => `<div class="row ed"><input data-n="${n}" data-k="name" value="${esc(i.name)}"><input data-n="${n}" data-k="price" type="number" value="${i.price}"><button class="ghost" data-on="${n}">${i.on === false ? 'Habis' : 'Ada'}</button><button class="ghost" data-q="${n}">+ Nota${cart[n] ? ' (' + cart[n] + ')' : ''}</button><button class="ghost" data-del="${n}">Hapus</button></div>`).join('')}</div>
    <button id="print" class="btn">Cetak nota</button><div id="nota" class="receipt"></div>`;
    $('#out').onclick = () => auth.signOut().then(() => location.reload());
    $('#add').onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target); m.push({ id: Date.now().toString(36), name: f.get('name'), cat: f.get('cat') || 'Menu', price: +f.get('price'), on: true }); await save(); draw(); };
    $('#print').onclick = () => {
      const rows = Object.entries(cart).map(([n, q]) => ({ ...m[n], q })); if (!rows.length) return;
      const tot = rows.reduce((s, r) => s + r.price * r.q, 0);
      $('#nota').innerHTML = `<b>${esc(c.name)}</b><div>${new Date().toLocaleString('id-ID')}</div><hr>${rows.map(r => `<div><span>${esc(r.name)}</span><span>${r.q} x ${rp(r.price)} = ${rp(r.q * r.price)}</span></div>`).join('')}<hr><div><b>Total</b><b>${rp(tot)}</b></div><p>Terima kasih</p>`;
      window.print(); cart = {}; draw();
    };
  };
  app.onchange = async e => { const d = e.target.dataset; if (d.k) { m[d.n][d.k] = d.k === 'price' ? +e.target.value : e.target.value; await save(); } };
  app.onclick = async e => {
    const d = e.target.dataset;
    if (d.on !== undefined) { m[d.on].on = m[d.on].on === false; await save(); draw(); }
    if (d.del !== undefined && confirm('Hapus menu ini?')) { m.splice(d.del, 1); cart = {}; await save(); draw(); }
    if (d.q !== undefined) { cart[d.q] = (cart[d.q] || 0) + 1; draw(); }
  };
  draw();
}

async function admin() {
  const u = auth.currentUser;
  if (!u) { app.innerHTML = '<h1>Cafeee Admin</h1>'; return login(admin); }
  const a = await db.collection('admins').doc(u.uid).get();
  if (!a.exists) return app.innerHTML = `<h1>Cafeee Admin</h1><p class="err">Akun ini belum jadi admin. Buat dokumen <b>admins/${u.uid}</b> di Firestore.</p>`;
  const snap = await cafes().orderBy('name').get();
  app.innerHTML = `<header class="top"><h1>Cafeee Admin</h1><span>${snap.size} toko</span></header>
  <form id="nw" class="add"><input name="slug" placeholder="slug-toko" pattern="[a-z0-9\\-]+" required><input name="name" placeholder="Nama toko" required><select name="plan"><option value="basic">Paket 100rb</option><option value="pro">Paket 200rb</option></select><input name="reviewUrl" placeholder="Link Google Review"><input name="ownerEmail" type="email" placeholder="Email pemilik (paket 200rb)"><button class="btn" style="margin:0">Buat toko</button></form>
  <div>${snap.docs.map(d => { const c = d.data(); return `<div class="row ed"><span style="flex:1 1 100%">${esc(c.name)} - ${c.plan === 'pro' ? '200rb' : '100rb'}${c.active === false ? ' (nonaktif)' : ''}</span><button class="ghost" data-qr="${d.id}" data-plan="${c.plan}">QR</button><button class="ghost" data-act="${d.id}">${c.active === false ? 'Aktifkan' : 'Nonaktifkan'}</button><button class="ghost" data-rv="${d.id}">Ubah link review</button><button class="ghost" data-rm="${d.id}">Hapus</button></div>`; }).join('')}</div><div id="qr"></div>`;
  $('#nw').onsubmit = async e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); const slug = f.slug; delete f.slug; await cafes().doc(slug).set({ ...f, menu: [], active: true }); admin(); };
  app.onclick = async e => {
    const d = e.target.dataset, ref = id => cafes().doc(id);
    if (d.qr) {
      const url = base + (d.plan === 'pro' ? '?c=' : '?r=') + d.qr;
      $('#qr').innerHTML = `<div class="card"><div id="q"></div><small>${esc(url)}</small><button id="dl" class="btn">Unduh PNG</button></div>`;
      new QRCode($('#q'), { text: url, width: 512, height: 512, correctLevel: QRCode.CorrectLevel.H });
      $('#dl').onclick = () => { const x = document.createElement('a'); x.href = $('#q canvas').toDataURL('image/png'); x.download = d.qr + '.png'; x.click(); };
    }
    if (d.act) { const s = await ref(d.act).get(); await ref(d.act).update({ active: s.data().active === false }); admin(); }
    if (d.rv) { const v = prompt('Link Google Review baru:'); if (v) { await ref(d.rv).update({ reviewUrl: v }); admin(); } }
    if (d.rm && confirm('Hapus toko ini permanen?')) { await ref(d.rm).delete(); admin(); }
  };
}
