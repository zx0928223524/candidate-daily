(function () {
  "use strict";

  var app = document.getElementById("app");
  var state = { counties: [], site: null, news: null, bios: null, hl: null, county: "全部", query: "", tab: "highlights" };

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

  function refs(list) {
    return (list || []).map(function (r) {
      return '<a class="src" href="' + esc(r.link) + '" target="_blank" rel="noopener" title="' + esc(r.title) + '">' + esc(r.source || "來源") + "</a>";
    }).join("、");
  }

  function points(list) {
    return list.map(function (p) {
      return '<div class="item"><div>' + esc(p.text) + '</div><div class="meta">來源：' + refs(p.refs) + "</div></div>";
    }).join("");
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
    var note = state.site && state.site.notice;
    return note ? '<div class="demo-bar">' + esc(note) + "</div>" : "";
  }

  function updated() {
    var u = (state.news && state.news.generatedAt) || (state.site && state.site.updatedAt);
    var s = u ? "資料更新時間：" + esc(u) : "資料更新時間：尚未更新（示範畫面）";
    if (state.news && state.news.failed && state.news.failed.length) {
      s += "。部分候選人這次更新失敗，顯示的是前一次的資料";
    }
    return s;
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

    var ov;
    if (state.hl && state.hl.overview && state.hl.overview.length) {
      ov = state.hl.overview.map(function (p) {
        return "<li>" + esc(p.text) + '<div class="meta">來源：' + refs(p.refs) + "</div></li>";
      }).join("");
      ov += '<li class="note meta">' + (state.hl.overviewMode === "ai"
        ? "以上重點由 AI 根據新聞標題整理，內容請以來源原文為準。"
        : "目前顯示的是各候選人最新的新聞標題，沒有經過 AI 整理。") + "</li>";
    } else {
      ov = '<li class="meta">今天還沒有整理好的重點。每天早上 7 點會自動更新。</li>';
    }

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
    var key = who.county + "_" + who.name;
    var h = state.hl && state.hl.items && state.hl.items[key];
    if (tab === "highlights") {
      if (!h || !h.points.length) return "<p>最近 14 天沒有找到和 " + n + " 有關的新聞，所以沒有今日重點。</p>";
      return points(h.points) + '<p class="meta note">' + (h.mode === "ai"
        ? "重點由 AI 根據新聞標題整理，內容請以來源原文為準。"
        : "目前顯示的是最新的新聞標題，沒有經過 AI 整理。") + "</p>";
    }
    if (tab === "bio") {
      var b = state.bios && state.bios.items && state.bios.items[key];
      if (!b) return "<p>目前找不到 " + n + " 可靠的公開資料。有新資料時，會在每天更新時補上。</p>";
      return "<p>" + esc(b.text).replace(/\n/g, "</p><p>") + "</p>" +
        '<p class="meta">資料來源：' + (b.url ? '<a href="' + esc(b.url) + '" target="_blank" rel="noopener">' + esc(b.source) + "</a>" : esc(b.source)) +
        "。內容僅供參考，請以原文為準。</p>";
    }
    if (tab === "news") {
      if (!state.news || !state.news.items) return "<p>新聞資料還沒有準備好。</p>";
      var list = state.news.items[key] || [];
      if (!list.length) return "<p>最近 14 天沒有找到和 " + n + " 有關的新聞。</p>";
      return list.map(function (x) {
        return '<div class="item"><a href="' + esc(x.link) + '" target="_blank" rel="noopener">' + esc(x.title) +
          '</a><div class="meta">' + esc(x.source) + "，" + esc(x.date) + "</div></div>";
      }).join("");
    }
    var sc = h && h.schedule || [];
    if (!sc.length) return "<p>目前沒有公開行程。行程只從新聞標題整理，沒有登在新聞上的行程不會出現在這裡。</p>";
    return sc.map(function (x) {
      return '<div class="item"><div>' + (x.date ? "<b>" + esc(x.date) + "</b>　" : "") + esc(x.text) +
        '</div><div class="meta">來源：' + refs([x.ref]) + "</div></div>";
    }).join("") + '<p class="meta note">行程只從新聞標題整理，可能不完整，請以來源原文為準。</p>';
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

  function optional(url) { return load(url).catch(function () { return null; }); }

  Promise.all([load("data/candidates.json"), load("data/site.json"), optional("data/news.json"), optional("data/bios.json"), optional("data/highlights.json")]).then(function (res) {
    state.counties = res[0].counties;
    state.site = res[1];
    state.news = res[2];
    state.bios = res[3];
    state.hl = res[4];
    window.addEventListener("hashchange", function () { state.tab = "highlights"; route(); });
    route();
  }).catch(function () {
    app.innerHTML = '<div class="wrap"><p class="empty">資料讀取失敗。請確認網路連線，稍後重新整理頁面。</p></div>';
  });
})();
