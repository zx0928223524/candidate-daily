#!/usr/bin/env python3
"""每天自動執行：用 AI 把新聞標題整理成「今日總覽」「每位候選人的重點」「已知行程」。

原則：
1. AI 只能看到新聞標題，只能寫標題明確提到的事，並且每一則都要附上來源編號。
2. 沒有金鑰、額度用完、或 AI 回傳格式不對時，改用「不用 AI 的簡單版」：直接列最新標題。
3. 任何一步失敗都不會讓頁面變空白，會保留前一次的資料。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TW = timezone(timedelta(hours=8))
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
GAP_SECONDS = 7          # 兩次呼叫之間的間隔，避免超過免費額度的每分鐘上限
MAX_TITLES = 10


class AIUnavailable(Exception):
    pass


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def ask(prompt, state):
    """呼叫 Gemini，回傳解析好的 JSON。遇到額度限制會等一下再試，並自動換備用模型。"""
    if not API_KEY:
        raise AIUnavailable("沒有金鑰")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }).encode()
    last = None
    for model in state["models"]:
        for attempt in range(3):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "x-goog-api-key": API_KEY})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    out = json.loads(r.read())
                text = out["candidates"][0]["content"]["parts"][0]["text"]
                state["used"] = model
                return json.loads(text)
            except urllib.error.HTTPError as e:
                code = e.code
                last = f"{model} HTTP {code}"
                if code == 429:
                    time.sleep(35 * (attempt + 1))
                    continue
                if code in (400, 403) :
                    # 金鑰無效、所在地區不支援等，換模型也不會好
                    raise AIUnavailable(f"HTTP {code}") from e
                break  # 404 等：換下一個模型
            except Exception as e:  # noqa: BLE001
                last = f"{model} {type(e).__name__}"
                time.sleep(3)
                continue
    raise AIUnavailable(last or "未知錯誤")


def ref_obj(it):
    return {"title": it["title"], "source": it["source"], "link": it["link"], "date": it["date"]}


def clean_points(raw, items, limit):
    """檢查 AI 回傳：每則都要有合理的來源編號，沒有就丟掉。"""
    out = []
    for p in (raw or [])[:limit]:
        try:
            text = str(p["text"]).strip()
            refs = [int(r) for r in p["refs"]]
        except Exception:  # noqa: BLE001
            continue
        refs = [r for r in refs if 1 <= r <= len(items)]
        if not text or len(text) > 90 or not refs:
            continue
        out.append({"text": text, "refs": [ref_obj(items[r - 1]) for r in refs[:3]]})
    return out


def clean_schedule(raw, items, today):
    out = []
    for s in (raw or [])[:5]:
        try:
            text = str(s["text"]).strip()
            ref = int(s["ref"])
            date = s.get("date")
        except Exception:  # noqa: BLE001
            continue
        if not (1 <= ref <= len(items)) or not text or len(text) > 90:
            continue
        if date is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)) or str(date) < today:
                continue
        out.append({"date": date, "text": text, "ref": ref_obj(items[ref - 1])})
    return out


def candidate_prompt(name, county, items, today):
    lines = "\n".join(f"[{i}] {x['date']} {x['source']}：{x['title']}" for i, x in enumerate(items, 1))
    return f"""你是中立的新聞整理助手。以下是 2026 年{county}長選舉候選人「{name}」最近的新聞標題，格式為「[編號] 日期 媒體：標題」。今天是 {today}。

{lines}

請只根據這些標題，輸出 JSON，格式如下：
{{"points":[{{"text":"一句話","refs":[編號]}}],"schedule":[{{"date":"YYYY-MM-DD 或 null","text":"行程描述","ref":編號}}]}}

規則：
1. points 最多 3 則，每則一句繁體中文（不超過 50 字），只能寫標題明確提到的事，不可推測，不可加入標題沒有的資訊，不要評論好壞，不要預測勝負。
2. 每則 points 都要附 refs（依據的標題編號，1 到 3 個）。
3. 同一件事的多則標題要合併成一則。
4. 標題中的質疑、指控、爆料，要寫成「某某指稱……」或「某某質疑……」，不可當成已確認的事實。
5. schedule 只放標題明確寫出日期或時間、且尚未發生（今天或之後）的公開行程，例如辯論會、政見會、造勢活動。日期不確定就填 null；沒有就給空陣列。
6. 只輸出 JSON。"""


def overview_prompt(items, today):
    lines = "\n".join(
        f"[{i}] {x['date']} {x['who']}（{x['county']}）{x['source']}：{x['title']}" for i, x in enumerate(items, 1))
    return f"""你是中立的新聞整理助手。以下是 2026 年縣市長選舉各候選人最近的新聞標題，格式為「[編號] 日期 候選人（縣市）媒體：標題」。今天是 {today}。

{lines}

請只根據這些標題，整理 3 到 5 則今天最值得看的選戰重點，輸出 JSON：
{{"points":[{{"text":"一句話","refs":[編號]}}]}}

規則：
1. 每則一句繁體中文（不超過 60 字），只能寫標題明確提到的事，不可推測，不可加入標題沒有的資訊，不要評論好壞，不要預測勝負。
2. 盡量涵蓋不同縣市、不同候選人，不偏袒任何一方。
3. 每則都要附 refs（依據的標題編號，1 到 3 個）。
4. 標題中的質疑、指控、爆料，要寫成「某某指稱……」，不可當成已確認的事實。
5. 只輸出 JSON。"""


def basic_points(items, n=3):
    """不用 AI 的簡單版：直接列最新的標題。"""
    return [{"text": x["title"], "refs": [ref_obj(x)]} for x in items[:n]]


def main():
    cands = load(DATA / "candidates.json", {"counties": []})["counties"]
    news = load(DATA / "news.json", {}).get("items", {})
    old = load(DATA / "highlights.json", {})
    today = datetime.now(TW).strftime("%Y-%m-%d")
    now = datetime.now(TW).strftime("%Y-%m-%d %H:%M")

    state = {"models": list(MODELS), "used": None}
    ai_ok = bool(API_KEY)
    ai_error = None if API_KEY else "沒有設定金鑰"
    consecutive = 0
    items_out, ai_count = {}, 0

    # 1. 每位候選人
    for c in cands:
        for name in c["candidates"]:
            key = f'{c["name"]}_{name}'
            items = (news.get(key) or [])[:MAX_TITLES]
            if not items:
                items_out[key] = {"points": [], "schedule": [], "mode": "none"}
                continue
            entry = {"points": basic_points(items), "schedule": [], "mode": "basic"}
            if ai_ok:
                try:
                    raw = ask(candidate_prompt(name, c["name"], items, today), state)
                    pts = clean_points(raw.get("points"), items, 3)
                    if pts:
                        entry = {"points": pts,
                                 "schedule": clean_schedule(raw.get("schedule"), items, today),
                                 "mode": "ai"}
                        ai_count += 1
                    consecutive = 0
                except AIUnavailable as e:
                    ai_error = str(e)
                    print("AI 無法使用：", key, e, file=sys.stderr)
                    consecutive += 1
                    if consecutive >= 4:
                        ai_ok = False
                except Exception as e:  # noqa: BLE001
                    print("AI 回傳格式有問題：", key, type(e).__name__, file=sys.stderr)
                time.sleep(GAP_SECONDS)
            items_out[key] = entry

    # 2. 今日總覽：每位候選人最多取 2 則最近 3 天的新聞，避免被特定人物的大量報導洗版
    pool = []
    names = {}
    for c in cands:
        for name in c["candidates"]:
            names[f'{c["name"]}_{name}'] = (c["name"], name)
    cutoff = (datetime.now(TW) - timedelta(days=3)).strftime("%Y-%m-%d")
    for key, lst in news.items():
        if key not in names:
            continue
        for x in [i for i in lst if i["date"] >= cutoff][:2]:
            pool.append(dict(x, who=names[key][1], county=names[key][0]))
    pool.sort(key=lambda x: x["date"], reverse=True)
    pool = pool[:45]

    overview, ov_mode = [], "none"
    if pool:
        seen, simple = set(), []
        for x in pool:  # 簡單版：不同候選人各取一則最新的
            if x["who"] in seen:
                continue
            seen.add(x["who"])
            simple.append(x)
        overview, ov_mode = basic_points(simple, 5), "basic"
        if ai_ok:
            try:
                raw = ask(overview_prompt(pool, today), state)
                pts = clean_points(raw.get("points"), pool, 5)
                if pts:
                    overview, ov_mode = pts, "ai"
            except Exception as e:  # noqa: BLE001
                print("總覽 AI 失敗：", type(e).__name__, e, file=sys.stderr)
    if not overview and old.get("overview"):
        overview, ov_mode = old["overview"], old.get("overviewMode", "basic")

    out = {"generatedAt": now, "model": state["used"], "overviewMode": ov_mode,
           "overview": overview, "items": items_out}
    (DATA / "highlights.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"完成：AI 整理 {ai_count} 位候選人，總覽模式 {ov_mode}，使用模型 {state['used']}，"
          f"AI 狀態 {'正常' if ai_ok else '不可用：' + str(ai_error)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
