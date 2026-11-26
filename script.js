/* ===== Cafeee - logika per halaman ===== */
const page = document.body.dataset.page;
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const qs = k => new URLSearchParams(location.search).get(k);

function bindLogin() {
  const m = $('#loginModal');
  const open = $('#openLogin') || $('#lock');
  open.onclick = () => { m.classList.add('on'); $('#u').focus(); };
  $('#x').onclick = () => m.classList.remove('on');
  $('#go').onclick = async () => {
    const to = await Auth.login($('#u').value.trim(), $('#p').value);
    if (to) location.href = to; else $('#msg').textContent = 'Username atau password salah, atau paket belum aktif.';
  };
}

const pages = {
  login: bindLogin,

  // QR/NFC selalu menuju r.html?c=slug -> diarahkan sesuai paket
  async redirect() {
    const d = await DB.load(), c = d.cafes.find(x => x.slug === qs('c'));
    if (!c || !c.active) return $('#s').textContent = 'Kartu ini belum aktif.';
    if (c.plan === 'pro') location.replace('menu.html?c=' + c.slug);
    else if (c.reviewUrl) location.replace(c.reviewUrl);
    else $('#s').textContent = 'Link review belum diisi.';
  },

  async menu() {
    bindLogin();
    const d = await DB.load(), c = d.cafes.find(x => x.slug === qs('c'));
    if (!c || !c.active) return $('#list').innerHTML = '<p class="center">Menu tidak ditemukan.</p>';
    $('#cname').textContent = c.name; document.title = 'Menu ' + c.name;
    const cats = [...new Set((c.menu || []).map(m => m.cat || 'Lainnya'))];
    $('#list').innerHTML = cats.length ? cats.map(k => `<h2 class="menu-cat">${esc(k)}</h2>` +
      c.menu.filter(m => (m.cat || 'Lainnya') === k).map(m => `<div class="item"><span>${esc(m.name)}</span><span class="price">${rp(m.price)}</span></div>`).join('')).join('')
      : '<p class="center">Menu belum diisi.</p>';
  },

  async dashboard() {
    const s = Auth.get(); if (!s || s.role !== 'cafe') return location.href = 'index.html';
    let d = await DB.load(), c = d.cafes.find(x => x.id === s.id), edit = null, cart = {};
    $('#cname').textContent = c.name; $('#viewMenu').href = 'menu.html?c=' + c.slug;
    const persist = () => DB.save(d);
    const draw = () => {
      $('#rows').innerHTML = (c.menu || []).map(m => `<tr><td>${esc(m.name)}<br><small>${esc(m.cat || '')}</small></td><td class="price">${rp(m.price)}</td>
        <td><button class="btn sm" data-e="${m.id}">Ubah</button> <button class="btn sm red" data-d="${m.id}">Hapus</button></td></tr>`).join('') || '<tr><td>Belum ada menu. Tambahkan menu pertamamu di atas.</td></tr>';
      $('#pick').innerHTML = (c.menu || []).map(m => `<button class="btn light" data-a="${m.id}">${esc(m.name)}<br><small>${rp(m.price)}</small></button>`).join('');
      const items = Object.entries(cart).map(([id, q]) => ({ ...c.menu.find(m => m.id === id), q })).filter(i => i.name);
      $('#cart').innerHTML = items.map(i => `<div class="item"><span>${esc(i.name)} x${i.q}</span><span>${rp(i.price * i.q)}</span></div>`).join('');
      $('#tot').textContent = 'Total ' + rp(items.reduce((a, i) => a + i.price * i.q, 0));
      return items;
    };
    $('#save').onclick = async () => {
      const n = $('#mn').value.trim(), p = +$('#mp').value; if (!n || p < 0) return;
      const obj = { id: edit || uid(), name: n, price: p, cat: $('#mc').value.trim() };
      c.menu = c.menu || [];
      const i = c.menu.findIndex(m => m.id === edit); i >= 0 ? c.menu[i] = obj : c.menu.push(obj);
      await persist(); edit = null; ['#mn', '#mp', '#mc'].forEach(x => $(x).value = ''); $('#ft').textContent = 'Tambah menu'; $('#cancel').style.display = 'none'; draw();
    };
    $('#cancel').onclick = () => { edit = null; ['#mn', '#mp', '#mc'].forEach(x => $(x).value = ''); $('#ft').textContent = 'Tambah menu'; $('#cancel').style.display = 'none'; };
    document.body.onclick = async e => {
      const t = e.target.dataset;
      if (t.e) { const m = c.menu.find(x => x.id === t.e); edit = m.id; $('#mn').value = m.name; $('#mp').value = m.price; $('#mc').value = m.cat || ''; $('#ft').textContent = 'Ubah menu'; $('#cancel').style.display = ''; scrollTo(0, 0); }
      if (t.d && confirm('Hapus menu ini?')) { c.menu = c.menu.filter(x => x.id !== t.d); await persist(); draw(); }
      if (t.a) { cart[t.a] = (cart[t.a] || 0) + 1; draw(); }
    };
    $('#clr').onclick = () => { cart = {}; draw(); };
    $('#print').onclick = () => {
      const items = draw(); if (!items.length) return;
      $('#nota').innerHTML = `<div style="text-align:center"><b>${esc(c.name)}</b><br>${new Date().toLocaleString('id-ID')}</div><hr>` +
        items.map(i => `<div>${esc(i.name)}</div><div class="l"><span>${i.q} x ${i.price}</span><span>${i.price * i.q}</span></div>`).join('') +
        `<hr><div class="l"><b>TOTAL</b><b>${rp(items.reduce((a, i) => a + i.price * i.q, 0))}</b></div><p style="text-align:center">Terima kasih!</p>`;
      print();
    };
    draw();
  },

  async admin() {
    const s = Auth.get(); if (!s || s.role !== 'owner') return location.href = 'index.html';
    let d = await DB.load(), edit = null;
    const link = c => baseUrl() + 'r.html?c=' + c.slug;
    const draw = () => {
      const pro = d.cafes.filter(c => c.plan === 'pro').length;
      $('#stats').innerHTML = [['Total klien', d.cafes.length], ['Paket Menu', pro], ['Perkiraan omzet', rp(pro * 200000 + (d.cafes.length - pro) * 100000)]]
        .map(([a, b]) => `<div class="panel coffee"><small>${a}</small><h2>${b}</h2></div>`).join('');
      $('#rows').innerHTML = d.cafes.map(c => `<tr><td><b>${esc(c.name)}</b><br><small>${c.slug}</small></td>
        <td><span class="tag ${c.plan === 'pro' ? 'pro' : ''}">${c.plan === 'pro' ? 'Menu 200rb' : 'Review 100rb'}</span></td>
        <td><button class="btn sm ${c.active ? '' : 'red'}" data-t="${c.id}">${c.active ? 'Aktif' : 'Nonaktif'}</button></td>
        <td><button class="btn sm" data-q="${c.id}">QR</button> <button class="btn sm light" data-e="${c.id}">Ubah</button> <button class="btn sm red" data-d="${c.id}">Hapus</button></td></tr>`).join('') || '<tr><td>Belum ada klien.</td></tr>';
    };
    const reset = () => { edit = null; ['#cn', '#cr', '#cu', '#cw'].forEach(x => $(x).value = ''); $('#cp').value = 'basic'; $('#ft').textContent = 'Tambah klien'; $('#cancel').style.display = 'none'; };
    $('#save').onclick = async () => {
      const name = $('#cn').value.trim(); if (!name) return;
      const old = d.cafes.find(x => x.id === edit);
      const c = old || { id: uid(), slug: slugify(name) + '-' + uid().slice(0, 3), menu: [], active: true };
      Object.assign(c, { name, plan: $('#cp').value, reviewUrl: $('#cr').value.trim(), user: $('#cu').value.trim() });
      if ($('#cw').value) c.passHash = await sha($('#cw').value);
      if (!old) d.cafes.push(c);
      await DB.save(d); reset(); draw();
    };
    $('#cancel').onclick = reset;
    document.body.onclick = async e => {
      const t = e.target.dataset;
      if (t.e) { const c = d.cafes.find(x => x.id === t.e); edit = c.id; $('#cn').value = c.name; $('#cp').value = c.plan; $('#cr').value = c.reviewUrl || ''; $('#cu').value = c.user || ''; $('#ft').textContent = 'Ubah klien'; $('#cancel').style.display = ''; scrollTo(0, 0); }
      if (t.d && confirm('Hapus klien ini beserta menunya?')) { d.cafes = d.cafes.filter(x => x.id !== t.d); await DB.save(d); draw(); }
      if (t.t) { const c = d.cafes.find(x => x.id === t.t); c.active = !c.active; await DB.save(d); draw(); }
      if (t.q) {
        const c = d.cafes.find(x => x.id === t.q); $('#qrbox').innerHTML = '';
        new QRCode($('#qrbox'), { text: link(c), width: 256, height: 256, correctLevel: QRCode.CorrectLevel.H });
        $('#qt').textContent = c.name; $('#qu').textContent = link(c) + '  (tulis URL ini ke kartu NFC)'; $('#qrModal').classList.add('on');
        $('#dl').onclick = () => { const cv = $('#qrbox canvas'); const a = document.createElement('a'); a.download = 'qr-' + c.slug + '.png'; a.href = cv.toDataURL('image/png'); a.click(); };
      }
    };
    $('#qx').onclick = () => $('#qrModal').classList.remove('on');
    draw();
  }
};
pages[page] && pages[page]();
