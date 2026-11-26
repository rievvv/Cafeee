/* ===== Cafeee - konfigurasi & lapisan data (dipakai semua halaman) ===== */
const CFG = {
  OWNER_USER: 'owner',
  OWNER_PASS: 'GANTI-PASSWORD-INI',
  // Isi dua baris ini agar data tersimpan online (Supabase). Kosong = mode demo (localStorage).
  SUPABASE_URL: '',   // contoh: https://xxxx.supabase.co
  SUPABASE_KEY: ''    // anon public key
};
const H = () => ({ apikey: CFG.SUPABASE_KEY, Authorization: 'Bearer ' + CFG.SUPABASE_KEY });
const DB = {
  async load() {
    if (CFG.SUPABASE_URL) {
      const r = await fetch(`${CFG.SUPABASE_URL}/rest/v1/kv?key=eq.cafeee&select=value`, { headers: H() });
      const j = await r.json();
      return (j[0] && j[0].value) || { cafes: [] };
    }
    return JSON.parse(localStorage.getItem('cafeee') || '{"cafes":[]}');
  },
  async save(d) {
    if (CFG.SUPABASE_URL) {
      await fetch(`${CFG.SUPABASE_URL}/rest/v1/kv`, {
        method: 'POST',
        headers: { ...H(), 'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates' },
        body: JSON.stringify({ key: 'cafeee', value: d })
      });
    } else localStorage.setItem('cafeee', JSON.stringify(d));
  }
};
const sha = async s => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))]
  .map(b => b.toString(16).padStart(2, '0')).join('');
const rp = n => 'Rp ' + Number(n).toLocaleString('id-ID');
const $ = s => document.querySelector(s);
const uid = () => Math.random().toString(36).slice(2, 9);
const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const baseUrl = () => location.href.replace(/[^/]*(\?.*)?(#.*)?$/, '');
const Auth = {
  get: () => JSON.parse(sessionStorage.getItem('cafeee_sess') || 'null'),
  out() { sessionStorage.removeItem('cafeee_sess'); location.href = 'index.html'; },
  async login(u, p) {
    if (u === CFG.OWNER_USER && p === CFG.OWNER_PASS) { sessionStorage.setItem('cafeee_sess', JSON.stringify({ role: 'owner' })); return 'admin.html'; }
    const d = await DB.load(), h = await sha(p);
    const c = d.cafes.find(x => x.user === u && x.passHash === h && x.plan === 'pro' && x.active);
    if (!c) return null;
    sessionStorage.setItem('cafeee_sess', JSON.stringify({ role: 'cafe', id: c.id }));
    return 'dashboard.html';
  }
};
