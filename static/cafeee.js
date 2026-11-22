(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf"]') || {}).content || "";
  var rp = function (n) { return "Rp " + Math.round(n).toLocaleString("id-ID"); };
  function post(url, body, asJson) {
    var opts = { method: "POST", headers: { "X-CSRF-Token": csrf } };
    if (asJson) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    else { var fd = new URLSearchParams(body || {}); opts.body = fd; }
    return fetch(url, opts).then(function (r) { return r.json().then(function (j) { j._status = r.status; return j; }); });
  }

  // confirm before destructive forms
  document.addEventListener("submit", function (e) {
    var m = e.target.getAttribute("data-confirm");
    if (m && !window.confirm(m)) e.preventDefault();
  });

  // copy buttons
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy]");
    if (!b) return;
    var text = b.getAttribute("data-copy"), old = b.textContent;
    var done = function () { b.textContent = "Tersalin"; setTimeout(function () { b.textContent = old; }, 1400); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { window.prompt("Salin link ini:", text); });
    else window.prompt("Salin link ini:", text);
  });

  // item dialog (menu page)
  var dlg = document.getElementById("itemDialog");
  if (dlg) {
    var f = dlg.querySelector("form");
    document.addEventListener("click", function (e) {
      var nb = e.target.closest("[data-new-item]"), eb = e.target.closest("[data-edit-item]");
      if (!nb && !eb) return;
      var d = eb ? JSON.parse(eb.getAttribute("data-edit-item")) : { id: "", name: "", description: "", price: "", category_id: "", available: 1 };
      dlg.querySelector("h2").textContent = eb ? "Ubah menu" : "Tambah menu";
      f.id.value = d.id; f.name.value = d.name; f.description.value = d.description || "";
      f.price.value = d.price; f.category_id.value = d.category_id || ""; f.available.checked = !!d.available;
      dlg.showModal(); f.name.focus();
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    dlg.querySelectorAll("[data-close]").forEach(function (b) { b.addEventListener("click", function () { dlg.close(); }); });
  }
  var cdlg = document.getElementById("catDialog");
  if (cdlg) {
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-cat]");
      if (!b) return;
      var d = JSON.parse(b.getAttribute("data-cat"));
      cdlg.querySelector("h2").textContent = d.id ? "Ubah kategori" : "Tambah kategori";
      cdlg.querySelector("[name=id]").value = d.id; cdlg.querySelector("[name=name]").value = d.name;
      cdlg.showModal(); cdlg.querySelector("[name=name]").focus();
    });
    cdlg.querySelectorAll("[data-close]").forEach(function (b) { b.addEventListener("click", function () { cdlg.close(); }); });
  }

  // inline price + stock toggle
  document.querySelectorAll(".price-input").forEach(function (inp) {
    inp.addEventListener("change", function () {
      post(inp.getAttribute("data-url"), { price: inp.value }).then(function (j) {
        if (j.ok) { inp.value = j.price; inp.classList.add("saved"); setTimeout(function () { inp.classList.remove("saved"); }, 1200); }
        else alert("Harga gagal disimpan. Muat ulang halaman lalu coba lagi.");
      });
    });
  });
  document.querySelectorAll(".toggle").forEach(function (t) {
    t.addEventListener("click", function () {
      post(t.getAttribute("data-url")).then(function (j) { if (j.ok) t.setAttribute("aria-pressed", j.available ? "true" : "false"); });
    });
  });

  // tag list: select all + print selected
  var all = document.getElementById("selAll");
  if (all) {
    all.addEventListener("change", function () { document.querySelectorAll(".selTag").forEach(function (c) { c.checked = all.checked; }); });
    var pb = document.getElementById("printSel");
    pb.addEventListener("click", function () {
      var ids = Array.prototype.map.call(document.querySelectorAll(".selTag:checked"), function (c) { return c.value; });
      if (!ids.length) { alert("Centang dulu kartu yang ingin dicetak."); return; }
      window.location = pb.getAttribute("data-url") + "?ids=" + ids.join(",");
    });
  }

  // public menu: search + category chips
  var search = document.getElementById("menuSearch");
  if (search) {
    search.addEventListener("input", function () {
      var v = search.value.trim().toLowerCase();
      document.querySelectorAll(".menu-sec").forEach(function (sec) {
        var any = false;
        sec.querySelectorAll("li").forEach(function (li) {
          var hit = !v || li.textContent.toLowerCase().indexOf(v) > -1;
          li.hidden = !hit; if (hit) any = true;
        });
        sec.hidden = !any;
      });
      var none = document.getElementById("noMatch"); if (none) none.hidden = !!document.querySelector(".menu-sec:not([hidden])");
    });
  }

  // POS
  var pos = document.getElementById("pos");
  if (pos) {
    var svc = parseFloat(pos.dataset.service) || 0, tax = parseFloat(pos.dataset.tax) || 0;
    var cart = {}, order = [];
    var $ = function (id) { return document.getElementById(id); };
    var totals = function () {
      var sub = 0; order.forEach(function (k) { sub += cart[k].price * cart[k].qty; });
      var s = Math.floor(sub * svc / 100 + 0.5), t = Math.floor((sub + s) * tax / 100 + 0.5);
      return { sub: sub, svc: s, tax: t, total: sub + s + t };
    };
    var render = function () {
      var box = $("cartLines"); box.innerHTML = "";
      if (!order.length) box.innerHTML = '<p class="muted">Ketuk menu di sebelah kiri untuk menambah pesanan.</p>';
      order.forEach(function (k) {
        var c = cart[k], row = document.createElement("div"); row.className = "line";
        row.innerHTML = '<b></b><span class="num right"></span><div class="qty"><button type="button" aria-label="Kurangi">−</button><span class="num"></span><button type="button" aria-label="Tambah">+</button></div><span class="muted small right"></span>';
        row.querySelector("b").textContent = c.name;
        row.querySelector(".num.right").textContent = rp(c.price * c.qty);
        row.querySelector(".qty .num").textContent = c.qty;
        row.querySelector(".small").textContent = rp(c.price) + " per porsi";
        var bs = row.querySelectorAll("button");
        bs[0].onclick = function () { c.qty--; if (c.qty < 1) { delete cart[k]; order.splice(order.indexOf(k), 1); } render(); };
        bs[1].onclick = function () { c.qty++; render(); };
        box.appendChild(row);
      });
      var t = totals();
      $("tSub").textContent = rp(t.sub);
      $("rowSvc").hidden = !svc; $("tSvc").textContent = rp(t.svc);
      $("rowTax").hidden = !tax; $("tTax").textContent = rp(t.tax);
      $("tTotal").textContent = rp(t.total);
      var cash = $("payment").value === "Tunai";
      $("cashBox").hidden = !cash;
      var paid = parseInt($("paid").value || "0", 10);
      $("tChange").textContent = cash && paid >= t.total && t.total ? rp(paid - t.total) : "-";
      $("saveBtn").disabled = !order.length;
    };
    var add = function (key, name, price) {
      if (!cart[key]) { cart[key] = { id: /^\d+$/.test(key) ? key : null, name: name, price: price, qty: 0 }; order.push(key); }
      cart[key].qty++; render();
    };
    pos.querySelectorAll(".tile").forEach(function (t) {
      t.addEventListener("click", function () { add(t.dataset.id, t.dataset.name, parseInt(t.dataset.price, 10)); });
    });
    pos.querySelectorAll(".chip[data-cat]").forEach(function (c) {
      c.addEventListener("click", function () {
        pos.querySelectorAll(".chip[data-cat]").forEach(function (x) { x.classList.toggle("on", x === c); });
        var cat = c.dataset.cat;
        pos.querySelectorAll(".tile").forEach(function (t) { t.hidden = cat !== "all" && t.dataset.cat !== cat; });
      });
    });
    $("posSearch").addEventListener("input", function () {
      var v = this.value.trim().toLowerCase();
      pos.querySelectorAll(".tile").forEach(function (t) { t.hidden = v && t.dataset.name.toLowerCase().indexOf(v) < 0; });
    });
    $("addCustom").addEventListener("click", function () {
      var n = $("cName").value.trim(), p = parseInt($("cPrice").value || "0", 10);
      if (!n || !(p >= 0)) { alert("Isi nama dan harga item."); return; }
      add("x" + Date.now(), n, p); $("cName").value = ""; $("cPrice").value = "";
    });
    $("payment").addEventListener("change", render);
    $("paid").addEventListener("input", render);
    document.querySelectorAll("[data-cash]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.dataset.cash === "pas" ? totals().total : parseInt(b.dataset.cash, 10);
        $("paid").value = v; render();
      });
    });
    $("saveBtn").addEventListener("click", function () {
      var btn = this; btn.disabled = true;
      var items = order.map(function (k) { var c = cart[k]; return c.id ? { id: c.id, qty: c.qty } : { name: c.name, price: c.price, qty: c.qty }; });
      post(pos.dataset.save, { items: items, table: $("table").value, payment: $("payment").value, paid: $("paid").value, note: $("note").value }, true)
        .then(function (j) {
          if (j.ok) window.location = j.url;
          else { alert(j.error || "Nota gagal disimpan."); btn.disabled = false; }
        }).catch(function () { alert("Koneksi bermasalah. Coba lagi."); btn.disabled = false; });
    });
    render();
  }
})();
