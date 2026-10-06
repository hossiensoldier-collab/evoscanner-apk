"""منابع گسترده: Papers with Code, Awesome, PyPI, RSS"""
import json, re, ssl, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

SSL = ssl.create_default_context()
SSL.check_hostname = False
SSL.verify_mode = ssl.CERT_NONE
try:
    from auth import get_token as _get_tok
    _TOKEN = _get_tok()
except Exception:
    _TOKEN = ""

UA = {"User-Agent": "Mozilla/5.0 EvoScanner/2.0"}
if _TOKEN:
    UA["Authorization"] = "token " + _TOKEN
    UA["Accept"] = "application/vnd.github+json"


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL) as r:
        return r.read().decode("utf-8", errors="ignore")


def paperswithcode(query, n=8):
    url = "https://paperswithcode.com/api/v1/papers/?" + urllib.parse.urlencode({
        "q": query, "items_per_page": n})
    try:
        data = json.loads(_get(url))
        out = []
        for r in data.get("results", []):
            out.append({
                "url": r.get("url_abs") or r.get("url_pdf") or "",
                "title": r.get("title", ""),
                "content": (r.get("abstract") or "")[:600],
                "source": "paperswithcode",
                "score": 0.9,
                "tags": "paper,research,code"})
        return out
    except Exception as e:
        print(f"  ! pwc: {e}"); return []


def awesome_lists(query, n=5):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
        "q": f"awesome {query} python", "sort": "stars",
        "order": "desc", "per_page": n})
    try:
        data = json.loads(_get(url))
        out = []
        for it in data.get("items", []):
            out.append({
                "url": it["html_url"],
                "title": it["full_name"],
                "content": (it.get("description") or "")[:500],
                "source": "awesome",
                "score": min(it.get("stargazers_count", 0) / 5000, 1.0),
                "tags": "awesome,curated"})
        return out
    except Exception as e:
        print(f"  ! awesome: {e}"); return []


def pypi_meta(query, n=8):
    url = f"https://pypi.org/search/?q={urllib.parse.quote(query)}"
    try:
        html = _get(url)
        names = re.findall(r'package-snippet__name">([^<]+)<', html)[:n]
        out = []
        for name in names:
            try:
                meta = json.loads(_get(f"https://pypi.org/pypi/{name}/json"))
                info = meta.get("info", {})
                out.append({
                    "url": f"https://pypi.org/project/{name}/",
                    "title": name,
                    "content": (info.get("summary","") or "") + "\n" +
                               (info.get("description","") or "")[:800],
                    "source": "pypi",
                    "score": 0.75,
                    "tags": f"pypi,{','.join(info.get('classifiers',[])[:3])}"})
            except Exception:
                continue
        return out
    except Exception as e:
        print(f"  ! pypi: {e}"); return []


RSS_FEEDS = {
    "realpython": "https://realpython.com/atom.xml",
    "pythonorg":  "https://www.python.org/blogs/rss/",
    "pycoder":    "https://pycoders.com/feed",
}


def rss_feed(key, n=10):
    url = RSS_FEEDS.get(key)
    if not url: return []
    try:
        raw = _get(url)
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//a:entry", ns) or root.findall(".//item")
        out = []
        for it in items[:n]:
            title = (it.findtext("a:title", default="", namespaces=ns) or
                     it.findtext("title") or "").strip()
            link = it.find("a:link", ns)
            url_v = link.get("href", "") if hasattr(link, "get") else \
                    (it.findtext("a:id", default="", namespaces=ns) or
                     it.findtext("link") or "")
            content = (it.findtext("a:summary", default="", namespaces=ns) or
                       it.findtext("description") or "")[:600]
            if title and url_v:
                out.append({
                    "url": url_v, "title": title,
                    "content": re.sub(r"<[^>]+>", " ", content)[:600],
                    "source": f"rss-{key}", "score": 0.65,
                    "tags": "article,blog"})
        return out
    except Exception as e:
        print(f"  ! rss-{key}: {e}"); return []


SCANNERS = {
    "paperswithcode": paperswithcode,
    "awesome":        awesome_lists,
    "pypi":           pypi_meta,
    "rss-realpython": lambda q, n=5: rss_feed("realpython", n),
    "rss-pythonorg":  lambda q, n=5: rss_feed("pythonorg", n),
    "rss-pyblog":     lambda q, n=5: rss_feed("pycoder", n),
}


def scan_all(query, n=5):
    results = []
    for name, fn in SCANNERS.items():
        try:
            results.extend(fn(query, n))
        except Exception as e:
            print(f"  ! {name}: {e}")
    return results

