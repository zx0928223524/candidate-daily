import urllib.request, urllib.parse, re, json, sys
UA = {"User-Agent": "candidate-daily/1.0 (personal, non-commercial project)"}
out = []
def probe(url, n=500):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            out.append(f"OK {r.status} {url}\n  final={r.geturl()}\n  type={r.headers.get('content-type')} len={len(b)}\n  head={b[:n].decode('utf-8','replace')!r}\n")
            return b
    except Exception as e:
        out.append(f"ERR {url}\n  {type(e).__name__}: {e}\n")
for u in [
  "https://tfc-taiwan.org.tw/rss.xml",
  "https://tfc-taiwan.org.tw/rss",
  "https://tfc-taiwan.org.tw/feed",
  "https://tfc-taiwan.org.tw/articles/report",
  "https://www.mygopen.com/feeds/posts/default?alt=rss&max-results=3",
  "https://www.mygopen.com/feeds/posts/default?alt=rss&max-results=3&q=" + urllib.parse.quote("選舉"),
  "https://www.mygopen.com/search?q=" + urllib.parse.quote("選舉"),
]:
    probe(u)
# Google News: site 篩選與連結還原
q = "(site:tfc-taiwan.org.tw OR site:mygopen.com) 選舉 when:30d"
b = probe("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", 1500)
if b:
    links = re.findall(rb"<link>([^<]+)</link>", b)
    if len(links) > 1:
        probe(links[1].decode(), 800)
open("probe/out.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out)[:6000])
