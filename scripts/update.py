#!/usr/bin/env python3
"""每天自動執行：蒐集各候選人的新聞與公開資料，寫進 data/ 資料夾。
只使用 Python 內建功能，不需要安裝任何額外套件。
某個候選人抓取失敗時，保留他前一次的資料，不會讓頁面變空白。"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TW = timezone(timedelta(hours=8))
UA = "candidate-daily/1.0 (personal, non-commercial project)"
NEWS_DAYS = 14
MAX_NEWS = 12


def get(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def norm(t):
    return re.sub(r"[\W_]+", "", t)


def fetch_news(county, name):
    q = f'"{name}" (選舉 OR 參選 OR {county}) when:{NEWS_DAYS}d'
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
           "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    root = ET.fromstring(get(url))
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3].strip()
        if name not in title:  # 標題沒提到這個人就不收，避免同名或不相關的新聞
            continue
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:  # noqa: BLE001
            continue
        if dt < cutoff:
            continue
        items.append({"title": title, "link": link, "source": source,
                      "date": dt.astimezone(TW).strftime("%Y-%m-%d"), "_dt": dt})
    items.sort(key=lambda x: x["_dt"], reverse=True)
    kept = []
    for x in items:  # 同一件事的重複報導合併：標題幾乎一樣就只留最新的一則
        if any(SequenceMatcher(None, norm(x["title"]), norm(k["title"])).ratio() > 0.8 for k in kept):
            continue
        kept.append(x)
    for x in kept:
        x.pop("_dt")
    return kept[:MAX_NEWS]


POLITICS = ["立法委員", "縣長", "市長", "議員", "政治人物", "政治家", "部長", "局長",
            "副市長", "副縣長", "黨", "候選人", "鄉長", "鎮長", "議長"]
TAIWAN = ["台灣", "臺灣", "中華民國"]


def fetch_bio(name):
    url = ("https://zh.wikipedia.org/w/api.php?action=query&format=json&prop=extracts%7Cinfo"
           "&exintro=1&explaintext=1&redirects=1&inprop=url&variant=zh-tw&titles=" +
           urllib.parse.quote(name))
    pages = json.loads(get(url))["query"]["pages"]
    page = next(iter(pages.values()))
    extract = (page.get("extract") or "").strip()
    if "missing" in page or not extract:
        return None
    if "可以指" in extract[:60] or "消歧義" in extract:
        return None
    if not any(w in extract for w in POLITICS) or not any(w in extract for w in TAIWAN):
        return None
    paras = [p.strip() for p in extract.split("\n") if p.strip()]
    text = "\n".join(paras[:2])
    if len(text) > 420:
        text = text[:420].rstrip("，、；") + "…"
    return {"text": text, "source": "維基百科", "url": page.get("fullurl", "")}


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def main():
    cands = load(DATA / "candidates.json", {"counties": []})["counties"]
    old_news = load(DATA / "news.json", {}).get("items", {})
    old_bios = load(DATA / "bios.json", {}).get("items", {})
    news, bios, failed = {}, {}, []

    for c in cands:
        for name in c["candidates"]:
            key = f'{c["name"]}_{name}'
            try:
                news[key] = fetch_news(c["name"], name)
            except Exception as e:  # noqa: BLE001
                print("新聞失敗", key, e, file=sys.stderr)
                news[key] = old_news.get(key, [])
                failed.append(key)
            time.sleep(0.5)
            try:
                b = fetch_bio(name)
                bios[key] = b
            except Exception as e:  # noqa: BLE001
                print("事蹟失敗", key, e, file=sys.stderr)
                bios[key] = old_bios.get(key)
            time.sleep(0.3)

    total = sum(len(c["candidates"]) for c in cands)
    now = datetime.now(TW).strftime("%Y-%m-%d %H:%M")
    if total and len(failed) > total * 0.5:
        # 超過一半失敗，多半是來源暫時有問題：不覆蓋舊資料，只記錄失敗
        meta = load(DATA / "news.json", {})
        meta["lastError"] = now
        (DATA / "news.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        print("失敗過多，保留舊資料", len(failed), "/", total)
        return 0

    with_news = sum(1 for v in news.values() if v)
    with_bio = sum(1 for v in bios.values() if v)
    (DATA / "news.json").write_text(json.dumps(
        {"generatedAt": now, "failed": failed, "items": news}, ensure_ascii=False), encoding="utf-8")
    (DATA / "bios.json").write_text(json.dumps(
        {"generatedAt": now, "items": bios}, ensure_ascii=False), encoding="utf-8")
    print(f"完成：{total} 位候選人，有新聞 {with_news} 位，有公開事蹟 {with_bio} 位，失敗 {len(failed)} 位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
