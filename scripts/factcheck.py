#!/usr/bin/env python3
"""每天自動執行：蒐集專業查核單位（台灣事實查核中心、MyGoPen 麥擱騙）發布的、
和 2026 縣市長選舉候選人有關的查核報告，整理成「流傳說法、查證結果、正確資訊、來源連結」。

原則：
1. 我們不自己判斷真假。「查證結果」一律沿用查核單位自己標示的結論。
2. AI 只能根據查核報告的文字改寫，不可加入報告沒有的資訊；報告沒有明確結論時，寫「請見原文」。
3. 沒有被查核單位處理過的傳言，不會出現在這裡，也不會被標成假的。
4. 沒有金鑰或 AI 失敗時，改用簡單版：直接放查核單位的標題和連結。
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize import AIUnavailable, ask, API_KEY, MODELS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TW = timezone(timedelta(hours=8))
UA = "candidate-daily/1.0 (personal, non-commercial project)"
DAYS = 120
MAX_NEW_AI = 40
GAP_SECONDS = 7
C = ["九合一", "選舉", "選票", "投票", "參選", "候選人", "縣長", "市長"]   # 一般性的搜尋字詞
ELECTION_WORDS = ["九合一", "縣市長", "縣長", "市長", "里長", "議員", "中選會", "選委會", "參選", "候選人", "選舉"]
VERDICTS = {"錯誤", "部分錯誤", "易誤解", "誤導", "事實釐清", "正確", "部分正確", "查證", "無法證實", "不實", "缺乏背景"}


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


def text_of(h):
    h = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", h or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def parse_feed(raw, source):
    out = []
    root = ET.fromstring(raw)
    ns = {"c": "http://purl.org/rss/1.0/modules/content/"}
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:  # noqa: BLE001
            continue
        body = it.findtext("c:encoded", namespaces=ns) or it.findtext("description") or ""
        out.append({"title": title, "link": link, "dt": dt, "source": source,
                    "text": text_of(body)[:2500],
                    "cats": [c.text for c in it.findall("category") if c.text]})
    return out


def search(term):
    q = urllib.parse.quote(term)
    res = []
    for source, url in (
        ("MyGoPen 麥擱騙", f"https://www.mygopen.com/feeds/posts/default?alt=rss&max-results=20&q={q}"),
        ("台灣事實查核中心", f"https://tfc-taiwan.org.tw/feed/?s={q}"),
    ):
        try:
            res += parse_feed(get(url), source)
        except Exception as e:  # noqa: BLE001
            print("查核來源失敗", source, term, type(e).__name__, file=sys.stderr)
        time.sleep(0.4)
    return res


def tag_of(title):
    m = re.match(r"\s*【([^】]+)】", title)
    return m.group(1).strip() if m else None


def strip_tag(title):
    return re.sub(r"^\s*【[^】]+】\s*", "", title).strip()


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def prompt(it):
    return f"""你是中立的查核報告整理助手。以下是專業查核單位「{it['source']}」發布的一篇文章，請只根據這篇文章的文字，輸出 JSON：
{{"skip":false,"claim":"網傳說法","verdict":"查核結論","truth":"正確資訊"}}

規則：
1. 如果這篇文章不是針對某個「網傳說法」的查核，或和 2026 年台灣縣市長或地方選舉、候選人完全無關，輸出 {{"skip":true}}。
2. claim：用一句繁體中文（不超過 50 字）寫出被查核的網傳說法，不要加評論。
3. verdict：只能是「錯誤、部分錯誤、易誤解、誤導、事實釐清、正確、部分正確、無法證實、請見原文」其中一個，必須是文章自己明確給出的結論；文章沒有明確結論就填「請見原文」。
4. truth：用 1 到 2 句繁體中文（不超過 120 字）寫出查證後的正確資訊，只能使用文章裡有的資訊，不可推測、不可加入文章沒有的內容，不要評論任何候選人或政黨。
5. 只輸出 JSON。

標題：{it['title']}
文章：{it['text'][:1800]}"""


def main():
    cands = load(DATA / "candidates.json", {"counties": []})["counties"]
    names = {}
    for c in cands:
        for n in c["candidates"]:
            names[n] = f'{c["name"]}_{n}'
    old = load(DATA / "factchecks.json", {})
    known = {x["link"]: x for x in old.get("items", [])}
    skipped = set(old.get("skipped", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)

    # 1. 蒐集：一般性字詞 + 每位候選人姓名
    pool = {}
    for term in C + list(names):
        for it in search(term):
            if it["dt"] < cutoff or "TOP10" in it["title"]:
                continue
            pool.setdefault(it["link"], it)

    # 2. 篩選：標題或內文要提到候選人，或標題明確和選舉有關
    keep = []
    for link, it in pool.items():
        blob = it["title"] + " " + it["text"]
        who = [k for n, k in names.items() if n in blob]
        if not who and not any(w in it["title"] for w in ELECTION_WORDS):
            continue
        it["who"] = who
        keep.append(it)
    keep.sort(key=lambda x: x["dt"], reverse=True)

    # 3. 整理：新的才呼叫 AI，已整理過的直接沿用
    state = {"models": list(MODELS), "used": None}
    ai_ok, new_ai, items = bool(API_KEY), 0, []
    for it in keep:
        link = it["link"]
        if link in skipped:
            continue
        verdict_tag = tag_of(it["title"])
        tag_verdict = verdict_tag if verdict_tag in VERDICTS else None
        if link in known and (known[link].get("ai") or not ai_ok or new_ai >= MAX_NEW_AI):
            prev = dict(known[link])
            prev["candidates"] = it["who"]
            items.append(prev)
            continue
        rec = {"link": link, "source": it["source"], "date": it["dt"].astimezone(TW).strftime("%Y-%m-%d"),
               "candidates": it["who"], "claim": strip_tag(it["title"]), "verdict": tag_verdict or "請見原文",
               "truth": "請點進查核報告閱讀完整說明。", "ai": False}
        if ai_ok and new_ai < MAX_NEW_AI:
            try:
                raw = ask(prompt(it), state)
                new_ai += 1
                time.sleep(GAP_SECONDS)
                if raw.get("skip"):
                    skipped.add(link)
                    continue
                claim, truth = str(raw.get("claim", "")).strip(), str(raw.get("truth", "")).strip()
                v = str(raw.get("verdict", "")).strip()
                if claim and truth and len(claim) <= 80 and len(truth) <= 200:
                    rec.update(claim=claim, truth=truth, ai=True,
                               verdict=tag_verdict or (v if v in VERDICTS else "請見原文"))
            except AIUnavailable as e:
                print("AI 無法使用：", e, file=sys.stderr)
                ai_ok = False
            except Exception as e:  # noqa: BLE001
                print("AI 回傳格式有問題：", type(e).__name__, file=sys.stderr)
        items.append(rec)

    items.sort(key=lambda x: x["date"], reverse=True)
    now = datetime.now(TW).strftime("%Y-%m-%d %H:%M")
    out = {"generatedAt": now, "items": items, "skipped": sorted(skipped)[-400:]}
    (DATA / "factchecks.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    with_cand = sum(1 for x in items if x["candidates"])
    print(f"完成：查核報告 {len(items)} 則（提到候選人的 {with_cand} 則），本次新整理 {new_ai} 則，"
          f"AI {'正常' if ai_ok else '不可用'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
