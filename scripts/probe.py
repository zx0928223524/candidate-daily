import urllib.request, urllib.parse, re, json, html
import xml.etree.ElementTree as ET
UA = {"User-Agent": "candidate-daily/1.0 (personal, non-commercial project)"}
out = []
def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()
def strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()
def log(*a): out.append(" ".join(str(x) for x in a))

q = urllib.parse.quote("選舉")
# 1 TFC WordPress API
try:
    d = json.loads(fetch(f"https://tfc-taiwan.org.tw/wp-json/wp/v2/posts?search={q}&per_page=6"))
    log("TFC wp-json items:", len(d), "keys:", sorted(d[0].keys()) if d else None)
    for p in d[:6]:
        c = strip(p.get("content", {}).get("rendered", ""))
        log("-", p["date"], p["link"], "|", strip(p["title"]["rendered"]), "| content len", len(c))
    if d:
        log("SAMPLE CONTENT:", strip(d[0]["content"]["rendered"])[:1500])
except Exception as e:
    log("TFC wp-json ERR", type(e).__name__, e)
# 2 TFC feed search
try:
    root = ET.fromstring(fetch(f"https://tfc-taiwan.org.tw/feed/?s={q}"))
    its = list(root.iter("item"))
    log("TFC feed ?s= items:", len(its))
    for it in its[:5]:
        log("-", it.findtext("pubDate"), it.findtext("link"), "|", it.findtext("title"))
except Exception as e:
    log("TFC feed ERR", type(e).__name__, e)
# 3 MyGoPen
try:
    root = ET.fromstring(fetch(f"https://www.mygopen.com/feeds/posts/default?alt=rss&max-results=5&q={q}"))
    its = list(root.iter("item"))
    log("MyGoPen items:", len(its))
    for it in its[:5]:
        cats = [c.text for c in it.findall("category")]
        log("-", it.findtext("pubDate"), it.findtext("link"), "|", it.findtext("title"), "| cats", cats[:6])
    if its:
        log("SAMPLE DESC:", strip(its[0].findtext("description") or "")[:1500])
except Exception as e:
    log("MyGoPen ERR", type(e).__name__, e)
open("probe/out.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
