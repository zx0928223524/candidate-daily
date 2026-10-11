(function () {
  "use strict";

  var app = document.getElementById("app");
  var state = { counties: [], site: null, county: "全部", query: "", tab: "highlights" };

  var TABS = [
    ["highlights", "今日重點"],
    ["bio", "事蹟"],
    ["news", "新聞"],
    ["schedule", "行程"]
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function total() {
    return state.counties.reduce(function (n, c) { return n + c.candidates.length; }, 0);
  }

  function id(county, name) { return encodeURIComponent(county + "_" + name); }

  function findCandidate(key) {
    var raw = decodeURIComponent(key);
    var i = raw.indexOf("_");
    var county = raw.slice(0, i), name = raw.slice(i + 1);
    for (var a = 0; a < state.counties.length; a++) {
      var c = state.counties[a];
      if (c.name === county && c.candidates.indexOf(name) > -1) return { county: county, name: name };
    }
    return null;
  }

  function demoBar() {
    return state.site && state.site.demo
      ? '<div class="demo-bar">目前是示範畫面，內容都是假資料，還沒有接上真實新聞。</div>'
      : "";
  }

  function updated() {
    var u = state.site && state.site.updatedAt;
    return u ? "資料更新時間：" + esc(u) : "資料更新時間：尚未更新（示範畫面）";
  }

  function home() {
    var q = state.query.trim();
    var chips = ["全部"].concat(state.counties.map(function (c) { return c.name; }));
    var chipHtml = chips.map(function (n) {
      return '<button class="chip" data-county="' + esc(n) + '" aria-pressed="' + (state.county === n) + '">' + esc(n) + "</button>";
    }).join("");

    var sections = state.counties
      .filter(function (c) { return state.county === "全部" || c.name === state.county; })
      .map(function (c) {
        var list = c.candidates.filter(function (n) { return !q || n.indexOf(q) > -1; });
        if (!list.length) return "";
        return '<section class="county"><h3>' + esc(c.name) + "，" + list.length + " 位</h3><div class=\"grid\">" +
          list.map(function (n) {
            return '<a class="card" href="#/c/' + id(c.name, n) + '"><span class="mono" aria-hidden="true">' +
              esc(n.charAt(0)) + "</span><b>" + esc(n) + "</b></a>";
          }).join("") + "</div></section>";
      }).join("");

    var ov = (state.site.overview || []).map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("");

    return demoBar() +
      '<div class="wrap">' +
      '<header class="top"><div class="brand">候選人大小事</div><nav class="nav"><a href="#/fake">假新聞專區</a></nav></header>' +
      '<p class="sub">2026 縣市長選舉，共 ' + total() + " 位候選人。" + updated() + "</p>" +
      "<h2>今日總覽</h2><ul class=\"overview\">" + ov + "</ul>" +
      '<h2>全部候選人</h2><div class="tools">' +
      '<input class="search" type="search" id="q" placeholder="搜尋候選人姓名" value="' + esc(state.query) + '" aria-label="搜尋候選人姓名">' +
      '<div class="chips" role="group" aria-label="依縣市篩選">' + chipHtml + "</div></div>" +
      (sections || '<p class="empty">找不到符合的候選人，請換個名字試試看。</p>') +
      "</div>";
  }

  function panel(tab, who) {
    var n = esc(who.name);
    if (tab === "highlights") {
      return "<p>示範：這裡會顯示 " + n + " 今天的 2 到 3 則重點，每則附上新聞來源。</p>";
    }
    if (tab === "bio") {
      return "<p>示範：這裡會整理 " + n + " 的基本資料、學經歷、重要經歷和公開爭議，每項都附上來源。</p>";
    }
    if (tab === "news") {
      return [1, 2, 3].map(function (i) {
        return '<div class="item"><div>示範新聞標題 ' + i + '</div><div class="meta">媒體名稱，日期</div></div>';
      }).join("");
    }
    return "<p>示範：這裡會列出 " + n + " 已公開的行程。找不到時，會寫「目前沒有公開行程」。</p>";
  }

  function candidate(key) {
    var who = findCandidate(key);
    if (!who) return notFound();
    var tabs = TABS.map(function (t) {
      return '<button class="tab" role="tab" data-tab="' + t[0] + '" aria-selected="' + (state.tab === t[0]) + '">' + t[1] + "</button>";
    }).join("");
    return demoBar() +
      '<div class="wrap">' +
      '<a class="back" href="#/">返回全部候選人</a>' +
      '<h1 class="who">' + esc(who.name) + "</h1>" +
      '<p class="where">' + esc(who.county) + "長候選人。" + updated() + "</p>" +
      '<div class="tabs" role="tablist">' + tabs + "</div>" +
      '<div class="panel" role="tabpanel">' + panel(state.tab, who) + "</div>" +
      "</div>";
  }

  function fake() {
    var items = (state.site.factchecks || []).map(function (f) {
      return '<article class="fc"><dl>' +
        "<dt>流傳說法</dt><dd>" + esc(f.claim) + "</dd>" +
        '<dt>查證結果</dt><dd><span class="badge">' + esc(f.verdict) + "</span></dd>" +
        "<dt>正確資訊</dt><dd>" + esc(f.truth) + "</dd>" +
        "<dt>來源</dt><dd>" + esc(f.source) + "</dd>" +
        "</dl></article>";
    }).join("");
    return demoBar() +
      '<div class="wrap">' +
      '<a class="back" href="#/">返回全部候選人</a>' +
      '<h1 class="who">假新聞專區</h1>' +
      '<p class="where">只整理專業查核單位已發布的結果，沒有被查核過的傳言不會標成假的。</p>' +
      items + "</div>";
  }

  function notFound() {
    return '<div class="wrap"><a class="back" href="#/">返回全部候選人</a><p class="empty">找不到這個頁面，請回到首頁重新選擇。</p></div>';
  }

  function route() {
    var h = location.hash || "#/";
    var html;
    if (h.indexOf("#/c/") === 0) html = candidate(h.slice(4));
    else if (h === "#/fake") html = fake();
    else html = home();
    app.innerHTML = html;
    document.title = "候選人大小事";
    bind(h);
    if (!state.keepScroll) window.scrollTo(0, 0);
    state.keepScroll = false;
  }

  function bind(h) {
    var q = document.getElementById("q");
    if (q) {
      q.addEventListener("input", function () {
        state.query = q.value; state.keepScroll = true;
        var pos = q.selectionStart;
        route();
        var nq = document.getElementById("q");
        nq.focus(); nq.setSelectionRange(pos, pos);
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll(".chip"), function (b) {
      b.addEventListener("click", function () { state.county = b.getAttribute("data-county"); state.keepScroll = true; route(); });
    });
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (b) {
      b.addEventListener("click", function () { state.tab = b.getAttribute("data-tab"); state.keepScroll = true; route(); });
    });
  }

  function load(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url);
      return r.json();
    });
  }

  Promise.all([load("data/candidates.json"), load("data/site.json")]).then(function (res) {
    state.counties = res[0].counties;
    state.site = res[1];
    window.addEventListener("hashchange", function () { state.tab = "highlights"; route(); });
    route();
  }).catch(function () {
    app.innerHTML = '<div class="wrap"><p class="empty">資料讀取失敗。請確認網路連線，稍後重新整理頁面。</p></div>';
  });
})();
