#!/usr/bin/env python3
"""
EvoScanner v0.2 — نسخه بهبودیافته
رفع PyPI + افزودن StackOverflow/Reddit/Dev.to + گزارش
"""

import hashlib, html, json, re, sqlite3, ssl, sys, time
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BASE = HOME / "evoscanner"
BASE.mkdir(exist_ok=True)
DB = BASE / "knowledge.db"
EVO = BASE / "evolution.json"
REPORT = BASE / "report.md"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE
UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "close",
}


# ─────────── پایگاه دانش ───────────

class KB:
    def __init__(self):
        self.conn = sqlite3.connect(DB)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS resources(
            hash TEXT PRIMARY KEY, url TEXT, title TEXT, content TEXT,
            source TEXT, score REAL, tags TEXT, found_at TEXT)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS queries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, source TEXT,
            new_hits INTEGER, ts TEXT)""")
        # migration: افزودن category اگر نبود
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(resources)")]
        if "category" not in cols:
            self.conn.execute("ALTER TABLE resources ADD COLUMN category TEXT DEFAULT 'other'")
        self.conn.commit()
        self._categorize_existing()

    def _categorize_existing(self):
        """دسته‌بندی خودکار منابعی که category ندارند"""
        rows = self.conn.execute(
            "SELECT hash, title, content, tags FROM resources WHERE category='other' OR category IS NULL"
        ).fetchall()
        for h, title, content, tags in rows:
            cat = categorize(title or "", content or "", tags or "")
            self.conn.execute("UPDATE resources SET category=? WHERE hash=?",
                              (cat, h))
        if rows:
            self.conn.commit()
            print(f"  🏷  {len(rows)} منبع دسته‌بندی شد")

    def add(self, url, title, content, source, score=0.5, tags=""):
        h = hashlib.sha256((url + title).encode()).hexdigest()[:16]
        title = html.unescape(title)
        content = html.unescape(content)
        cat = categorize(title, content, tags)
        try:
            self.conn.execute(
                "INSERT INTO resources(hash,url,title,content,source,score,tags,found_at,category) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (h, url, title, content[:800], source, score, tags,
                 datetime.now().isoformat(), cat))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"  ! add error: {e}")
            return False

    def log(self, q, src, new):
        self.conn.execute("INSERT INTO queries(query,source,new_hits,ts) VALUES(?,?,?,?)",
            (q, src, new, datetime.now().isoformat()))
        self.conn.commit()

    def total(self):
        return self.conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]

    def stats(self):
        return self.conn.execute(
            "SELECT source, COUNT(*), AVG(score) FROM resources GROUP BY source"
        ).fetchall()

    def search(self, term, limit=20):
        return self.conn.execute(
            """SELECT source, title, url, score FROM resources
               WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
               ORDER BY score DESC LIMIT ?""",
            (f"%{term}%", f"%{term}%", f"%{term}%", limit)).fetchall()

    def best_queries(self, limit=10):
        return self.conn.execute(
            """SELECT query, SUM(new_hits) as t FROM queries
               GROUP BY query ORDER BY t DESC LIMIT ?""", (limit,)).fetchall()

    def categories_stats(self):
        return self.conn.execute(
            """SELECT category, COUNT(*), AVG(score)
               FROM resources GROUP BY category ORDER BY COUNT(*) DESC"""
        ).fetchall()

    def by_category(self, cat, limit=50):
        return self.conn.execute(
            """SELECT source, title, url, score FROM resources
               WHERE category=? ORDER BY score DESC LIMIT ?""",
            (cat, limit)).fetchall()

    def by_source(self, src, limit=100):
        return self.conn.execute(
            """SELECT title, url, score FROM resources
               WHERE source=? ORDER BY score DESC LIMIT ?""", (src, limit)).fetchall()




# ─────────── Health Tracker ───────────
_HEALTH_FILE = BASE / "health.json"

class Health:
    """ردیابی سلامت منابع — بعد از ۳ خطای متوالی، منبع خاموش می‌شود"""
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if _HEALTH_FILE.exists():
            try:
                return json.loads(_HEALTH_FILE.read_text())
            except Exception:
                pass
        return {}

    def _save(self):
        _HEALTH_FILE.write_text(json.dumps(self.data, indent=2))

    def is_ok(self, name):
        return self.data.get(name, {}).get("fails", 0) < 3

    def ok(self, name):
        d = self.data.setdefault(name, {})
        d["fails"] = 0
        d["last_ok"] = datetime.now().isoformat()
        self._save()

    def fail(self, name):
        d = self.data.setdefault(name, {})
        d["fails"] = d.get("fails", 0) + 1
        d["last_fail"] = datetime.now().isoformat()
        self._save()
        if d["fails"] >= 3:
            print(f"  ⚠ {name} خاموش شد (۳ خطای متوالی)")

    def summary(self):
        return [(k, v.get("fails", 0)) for k, v in self.data.items()]




# ─────────── دسته‌بندی خودکار ───────────
CATEGORIES = {
    "async":      ["async", "asyncio", "await", "concurren", "aiohttp", "sanic"],
    "web":        ["flask", "django", "fastapi", "web", "http", "rest", "api"],
    "ml-ai":      ["machine learning", "ml", "ai", "neural", "deep", "llm",
                   "transformer", "gpt", "model", "training", "pytorch",
                   "tensorflow", "scikit", "gradio"],
    "testing":    ["test", "pytest", "unittest", "coverage", "mock"],
    "data":       ["pandas", "numpy", "data science", "dataframe", "csv",
                   "database", "sql", "sqlite", "postgres"],
    "security":   ["security", "vulnerab", "crypto", "auth", "cve", "injection"],
    "performance":["performance", "benchmark", "optim", "speed", "memory",
                   "profil", "cache"],
    "typing":     ["typing", "type hint", "mypy", "pydantic", "dataclass"],
    "patterns":   ["design pattern", "pattern", "architecture", "solid",
                   "refactor"],
    "packaging":  ["poetry", "pip", "package", "setuptools", "wheel", "pypi"],
    "parsing":    ["regex", "parse", "scrap", "beautifulsoup", "lxml",
                   "selenium"],
    "devops":     ["docker", "kubernetes", "ci", "cd", "deploy", "pipeline"],
}


def categorize(title, content="", tags=""):
    """تشخیص دسته بر اساس کلمات کلیدی"""
    text = (title + " " + content + " " + tags).lower()
    hits = []
    for cat, words in CATEGORIES.items():
        score = sum(1 for w in words if w in text)
        if score > 0:
            hits.append((cat, score))
    hits.sort(key=lambda x: -x[1])
    return hits[0][0] if hits else "other"



# ─────────── HTTP ───────────

def get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read().decode("utf-8", errors="ignore")


# ─────────── اسکنرها ───────────

def github(q, n=5):
    import random
    page = random.randint(1, 5)
    sort_by = random.choice(["stars", "updated", "forks"])
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
        "q": f"{q} language:python", "sort": sort_by,
        "order": "desc", "per_page": n, "page": page})
    try:
        data = json.loads(get(url))
        out = []
        for it in data.get("items", []):
            out.append({
                "url": it["html_url"], "title": it["full_name"],
                "content": (it.get("description") or "")[:500],
                "source": "github",
                "score": min(max(it.get("stargazers_count", 0), 50) / 5000, 1.0),
                "tags": "repo,python"})
        return out
    except Exception as e:
        print(f"  ! github: {e}"); return []


def arxiv(q, n=5):
    """فقط دسته‌های مرتبط با برنامه‌نویسی و AI"""
    cat_filter = "(cat:cs.SE OR cat:cs.PL OR cat:cs.AI OR cat:cs.LG OR cat:cs.CL)"
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": f"all:{q} AND {cat_filter}",
        "start": 0, "max_results": n,
        "sortBy": "submittedDate", "sortOrder": "descending"})
    try:
        root = ET.fromstring(get(url))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for e in root.findall("a:entry", ns):
            title = e.find("a:title", ns).text.strip().replace("\n", " ")
            summary = e.find("a:summary", ns).text.strip().replace("\n", " ")
            link = e.find("a:id", ns).text
            cats = [c.get("term") for c in e.findall("a:category", ns)]
            out.append({
                "url": link, "title": title,
                "content": summary[:600], "source": "arxiv",
                "score": 0.85, "tags": ",".join(cats)})
        return out
    except Exception as e:
        print(f"  ! arxiv: {e}"); return []


def stackoverflow(q, n=5):
    """Stack Overflow API — بدون کلید، سهمیه ۳۰۰ در روز"""
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode({
        "order": "desc", "sort": "votes",
        "q": q, "tagged": "python",
        "site": "stackoverflow", "pagesize": n,
        "filter": "withbody"})
    try:
        data = json.loads(get(url))
        out = []
        for it in data.get("items", []):
            body = re.sub(r"<[^>]+>", "", it.get("body", ""))[:500]
            out.append({
                "url": it["link"],
                "title": it["title"],
                "content": body,
                "source": "stackoverflow",
                "score": min(it.get("score", 0) / 100, 1.0),
                "tags": ",".join(it.get("tags", []))})
        return out
    except Exception as e:
        print(f"  ! stackoverflow: {e}"); return []


def hackernews(q, n=5):
    """HN Algolia + fallback به Lobsters"""
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({
        "query": f"python {q}", "tags": "story",
        "numericFilters": "points>20", "hitsPerPage": n})
    try:
        data = json.loads(get(url))
        out = []
        for it in data.get("hits", []):
            out.append({
                "url": it.get("url") or f"https://news.ycombinator.com/item?id={it['objectID']}",
                "title": it.get("title", ""),
                "content": (it.get("story_text") or "")[:500],
                "source": "hackernews",
                "score": min(it.get("points", 0) / 500, 1.0),
                "tags": "hn,python"})
        if out:
            return out
    except Exception as e:
        print(f"  ! hackernews: {e}")

    # fallback: Lobsters
    return lobsters(q, n)


def lobsters(q, n=5):
    """Lobsters — جایگزین HN، بدون Cloudflare"""
    url = "https://lobste.rs/search.json?" + urllib.parse.urlencode({
        "q": f"python {q}", "what": "stories",
        "order": "relevance", "page": 1})
    try:
        data = json.loads(get(url))
        out = []
        for it in data[:n]:
            out.append({
                "url": it.get("url") or it.get("comments_url", ""),
                "title": it.get("title", ""),
                "content": (it.get("description") or "")[:500],
                "source": "lobsters",
                "score": min(it.get("score", 0) / 50, 1.0),
                "tags": ",".join(it.get("tags", []))})
        return out
    except Exception as e:
        print(f"  ! lobsters: {e}"); return []


def devto(q, n=5):
    """Dev.to — با timeout کوتاه"""
    url = "https://dev.to/api/articles?" + urllib.parse.urlencode({
        "tag": "python", "per_page": n, "top": 365})
    try:
        data = json.loads(get(url, timeout=8))
        out = []
        for it in data[:n]:
            out.append({
                "url": it["url"],
                "title": it["title"],
                "content": (it.get("description") or "")[:500],
                "source": "devto",
                "score": 0.6,
                "tags": ",".join(it.get("tag_list", []))})
        return out
    except Exception as e:
        print(f"  ! devto: {e}"); return []



def gitlab(q, n=5):
    """GitLab API — جایگزین پایدار GitHub"""
    url = "https://gitlab.com/api/v4/projects?" + urllib.parse.urlencode({
        "search": f"python {q}", "order_by": "star_count",
        "sort": "desc", "per_page": n})
    try:
        data = json.loads(get(url, timeout=10))
        out = []
        for it in data[:n]:
            out.append({
                "url": it["web_url"],
                "title": it["path_with_namespace"],
                "content": (it.get("description") or "")[:500],
                "source": "gitlab",
                "score": min(it.get("star_count", 0) / 5000, 1.0),
                "tags": "gitlab,repo"})
        return out
    except Exception as e:
        print(f"  ! gitlab: {e}"); return []


SCANNERS = [
    ("github", github),
    ("arxiv", arxiv),
    ("stackoverflow", stackoverflow),
    ("gitlab", gitlab),
    ("devto", devto),
]


# ─────────── موتور تکامل ───────────

BASE_TOPICS = [
    "python asyncio", "python machine learning", "python typing",
    "python testing", "python performance", "python web framework",
    "python security", "python design patterns", "python packaging",
    "python concurrency", "python data science", "python fastapi",
    "python pydantic", "python poetry", "python debugging",
]

MUTATORS = [
    "{} 2025", "{} 2026", "best {}", "advanced {}",
    "{} benchmark", "{} tutorial", "{} best practices",
    "{} production", "{} patterns",
]


class Evolver:
    def __init__(self, kb):
        self.kb = kb
        self.state = self._load()

    def _load(self):
        if EVO.exists():
            return json.loads(EVO.read_text())
        return {"cycle": 0, "active": list(BASE_TOPICS),
                "retired": [], "history": []}

    def _save(self):
        EVO.write_text(json.dumps(self.state, indent=2))

    def next_queries(self, n=6):
        best = [q for q, _ in self.kb.best_queries(5)]
        pool = list(dict.fromkeys(best + self.state["active"]))
        return pool[:n]

    def evolve(self):
        import random
        self.state["cycle"] += 1
        scores = {q: t for q, t in self.kb.best_queries(100)}

        survivors = []
        for q in self.state["active"]:
            if q not in scores or scores[q] > 0:
                survivors.append(q)
            else:
                self.state["retired"].append(q)

        if scores:
            top3 = sorted(scores, key=scores.get, reverse=True)[:3]
            for best_q in top3:
                for _ in range(2):
                    new = random.choice(MUTATORS).format(best_q)
                    if new not in survivors:
                        survivors.append(new)

        while len(survivors) < 10:
            for t in BASE_TOPICS:
                if t not in survivors:
                    survivors.append(t); break

        self.state["active"] = survivors[:15]
        self.state["history"].append({
            "cycle": self.state["cycle"],
            "active": len(survivors),
            "retired_total": len(self.state["retired"]),
            "ts": datetime.now().isoformat()})
        self._save()
        return self.state["active"]


# ─────────── گزارش ───────────

def write_report(kb, evo):
    lines = [
        f"# گزارش EvoScanner v0.2",
        f"\n**تاریخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**چرخه:** {evo.state['cycle']}",
        f"**کل منابع:** {kb.total()}\n",
        "## آمار منابع\n",
        "| منبع | تعداد | میانگین امتیاز |",
        "|---|---|---|",
    ]
    for src, cnt, avg in kb.stats():
        lines.append(f"| {src} | {cnt} | {avg:.2f} |")

    lines.append("\n## بهترین منابع گیت‌هاب\n")
    for title, url, score in kb.by_source("github", 10):
        lines.append(f"- [{title}]({url}) — ⭐ {score:.2f}")

    lines.append("\n## پژوهش‌های arXiv\n")
    for title, url, score in kb.by_source("arxiv", 10):
        lines.append(f"- [{title}]({url})")

    lines.append("\n## دسته‌بندی منابع\n")
    lines.append("| دسته | تعداد | میانگین امتیاز |")
    lines.append("|---|---|---|")
    for cat, cnt, avg in kb.categories_stats():
        lines.append(f"| {cat} | {cnt} | {avg:.2f} |")

    lines.append("\n## برترین منابع هر دسته\n")
    for cat, cnt, avg in kb.categories_stats()[:8]:
        lines.append(f"\n### {cat} ({cnt} مورد)\n")
        for src, title, url, score in kb.by_category(cat, 5):
            lines.append(f"- [{title}]({url}) — `{src}` ⭐ {score:.2f}")

    lines.append("\n## دسته‌بندی منابع\n")
    lines.append("| دسته | تعداد | میانگین امتیاز |")
    lines.append("|---|---|---|")
    for cat, cnt, avg in kb.categories_stats():
        lines.append(f"| {cat} | {cnt} | {avg:.2f} |")

    lines.append("\n## برترین منابع هر دسته\n")
    for cat, cnt, avg in kb.categories_stats()[:8]:
        lines.append(f"\n### {cat} ({cnt} مورد)\n")
        for src, title, url, score in kb.by_category(cat, 5):
            lines.append(f"- [{title}]({url}) — `{src}` ⭐ {score:.2f}")

    lines.append("\n## کوئری‌های فعال\n")
    for q in evo.state["active"][:15]:
        lines.append(f"- `{q}`")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"📄 گزارش نوشته شد: {REPORT}")


# ─────────── حلقه اصلی ───────────

def one_cycle(kb, evo, queries, health=None):
    cycle = evo.state["cycle"] + 1
    print(f"\n═══ چرخه {cycle} ═══")
    if health:
        dead = [n for n, _ in health.summary() if not health.is_ok(n)]
        if dead:
            print(f"  💤 منابع خاموش: {', '.join(dead)}")
    total_new = 0
    for q in queries:
        for name, fn in SCANNERS:
            if health and not health.is_ok(name):
                continue
            try:
                results = fn(q)
                new = 0
                for r in results:
                    if kb.add(r["url"], r["title"], r["content"],
                              r["source"], r["score"], r.get("tags", "")):
                        new += 1; total_new += 1
                        print(f"  + [{r['source']}] {r['title'][:70]}")
                kb.log(q, name, new)
                if health:
                    if results:
                        health.ok(name)
                    else:
                        # اگر exception گرفته و لیست خالی برگرداند
                        health.fail(name)
            except Exception as e:
                if health:
                    health.fail(name)
                print(f"  ! {name}: {e}")
    print(f"\nجدید: {total_new} | کل: {kb.total()}")
    evo.evolve()
    return total_new


def show_stats(kb, evo):
    print("\n📊 پایگاه دانش:")
    for src, cnt, avg in kb.stats():
        print(f"  {src:15s} {cnt:5d} | میانگین {avg:.2f}")
    print(f"  کل: {kb.total()} | چرخه: {evo.state['cycle']}")



# ─────────── کاوشگر تعاملی ───────────

def explore(kb, evo):
    """حالت گفتگو با پایگاه دانش"""
    print("\n" + "═" * 55)
    print("  🔍 کاوشگر دانش — پایگاه پایتون و AI")
    print("═" * 55)
    print("  دستورات:")
    print("    /help         راهنما")
    print("    /cats         دسته‌ها")
    print("    /gaps         شکاف‌های دانشی")
    print("    /path <topic> مسیر یادگیری")
    print("    /quit         خروج")
    print("  یا فقط یک کلمه/سؤال بنویس.")
    print("═" * 55)

    while True:
        try:
            q = input("\n❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nخداحافظ"); return

        if not q:
            continue
        if q in ("/quit", "/exit", "/q"):
            print("خداحافظ"); return
        if q == "/help":
            print("  /cats /gaps /path /quit — یا هر چیزی بنویس")
            continue
        if q == "/cats":
            for cat, cnt, avg in kb.categories_stats():
                bar = "█" * min(cnt, 30)
                print(f"  {cat:12s} {cnt:4d}  {bar}")
            continue
        if q == "/gaps":
            cats = dict((c, n) for c, n, _ in kb.categories_stats())
            weak = [c for c in CATEGORIES if cats.get(c, 0) < 3]
            if weak:
                print("  📉 دسته‌های ضعیف:")
                for c in weak:
                    print(f"    • {c}  ({cats.get(c, 0)} منبع)")
                print("\n  پیشنهاد: کوئری‌های مرتبط را در evolution.json اضافه کن")
            else:
                print("  ✅ همه دسته‌ها پوشش کافی دارند")
            continue
        if q.startswith("/path "):
            topic = q[6:].strip()
            print_learning_path(kb, topic)
            continue

        # جستجوی عادی
        results = kb.search(q, 10)
        if not results:
            print(f"  ✗ چیزی برای '{q}' پیدا نشد")
            continue
        print(f"\n  📚 {len(results)} نتیجه:\n")
        for i, (src, title, url, score) in enumerate(results, 1):
            cat = categorize(title, "", "") if hasattr(sys.modules[__name__], "categorize") else "?"
            print(f"  {i:2d}. [{src:14s}] {title[:60]}")
            print(f"      {url}")
            if score >= 0.9:
                print(f"      ⭐ امتیاز بالا")


def print_learning_path(kb, topic):
    """مسیر یادگیری از مبتدی تا پیشرفته برای یک موضوع"""
    print(f"\n  🎯 مسیر یادگیری: {topic}")
    print("  " + "─" * 50)

    steps = [
        ("مبتدی",   [topic, f"{topic} tutorial", f"{topic} basics", f"{topic} intro"]),
        ("متوسط",   [f"{topic} advanced", f"{topic} patterns", f"{topic} best practices"]),
        ("پیشرفته", [f"{topic} internals", f"{topic} performance", f"{topic} production"]),
        ("پژوهش",   [f"{topic} research", f"{topic} paper", f"{topic} state of the art"]),
    ]

    for level, queries in steps:
        found = []
        for q in queries:
            r = kb.search(q, 3)
            found.extend(r)
        # حذف تکراری
        seen = set(); uniq = []
        for r in found:
            if r[2] not in seen:
                seen.add(r[2]); uniq.append(r)
        print(f"\n  ◆ {level} ({len(uniq)} منبع)")
        if not uniq:
            print("    (خالی — نیاز به جمع‌آوری بیشتر)")
        for src, title, url, score in uniq[:3]:
            print(f"    • [{src}] {title[:60]}")
            print(f"      {url}")


def main():
    kb = KB(); evo = Evolver(kb); health = Health()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "learn":
            from feedback import FeedbackHunter
            fh = FeedbackHunter(kb)
            if len(sys.argv) > 2 and sys.argv[2] == "report":
                fh.report(); return
            if len(sys.argv) > 2 and sys.argv[2] == "weak":
                weak = fh.weak_queries()
                if not weak:
                    print("  ✓ کوئری ضعیفی نیست")
                else:
                    print("\n📉 کوئری‌های ضعیف:\n")
                    for q, s in weak:
                        print(f"  {q[:50]:50s} avg={s['avg']:.2f} tries={s['tried']}")
                return
            # انتخاب ۶ کوئری جدید
            qs = fh.select(6)
            print("\n🎯 کوئری‌های انتخابی UCB:\n")
            for q in qs:
                print(f"  • {q}")
            state = evo.state
            state["active"] = list(dict.fromkeys(state["active"] + qs))[:30]
            evo._save()
            print(f"\n  ✓ به لیست فعال اضافه شد")
            return

        if cmd == "discover":
            from discover import discover, propose_cats
            k = int(sys.argv[2]) if len(sys.argv) > 2 else 6
            props = discover(kb, k=k)
            new_cats = propose_cats(props)
            if new_cats:
                print(f"\n💡 برای افزودن دسته‌های جدید:")
                for c in new_cats:
                    print(f"   • {c}")
            return

        if cmd == "compress":
            from compress import merge_similar_entities, archive_old, report
            from graph import Graph
            g = Graph()
            print("\n📦 فشرده‌سازی...\n")
            m = merge_similar_entities(g, min_cooc=2)
            print(f"  ✓ {m} موجودیت ادغام شد")
            a = archive_old(kb, min_age_days=60, max_score=0.4)
            print(f"  ✓ {a} منبع آرشیو شد")
            report(g, kb)
            return

        if cmd == "compress-report":
            from compress import report
            from graph import Graph
            report(Graph(), kb); return

        if cmd == "ask":
            from rag import ask
            q = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            if not q:
                print("استفاده: ask <سؤال>"); return
            ask(kb, q); return

        if cmd == "goal":
            from goals import show_goal, list_goals, goal_queries
            if len(sys.argv) < 3:
                list_goals(); return
            g = sys.argv[2]
            show_goal(kb, g)
            qs = goal_queries(g)
            if qs:
                state = evo.state
                state["active"] = list(dict.fromkeys(
                    state["active"] + qs))[:30]
                evo._save()
                print(f"\n  ✓ {len(qs)} کوئری به صف اضافه شد")
            return

        if cmd == "goals":
            from goals import list_goals
            list_goals(); return

        if cmd == "daemon":
            import subprocess
            args = [sys.executable, "daemon.py"] + sys.argv[2:]
            subprocess.run(args, cwd=str(Path.home() / "evoscanner"))
            return

        if cmd == "graph-peers":
            from graph import Graph
            if len(sys.argv) < 3:
                print("استفاده: graph-peers <entity>"); return
            node = sys.argv[2]
            print(f"\n👥 پکیج‌های هم‌دسته با '{node}':\n")
            peers = Graph().category_peers(node)
            if not peers:
                print("  (چیزی یافت نشد)")
            for other, w in peers:
                print(f"  {other:30s} وزن {w}")
            return

        if cmd == "enrich":
            from fetcher import enrich_top
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            enrich_top(kb, limit=n); return

        if cmd == "rebuild":
            from graph import Graph
            from classifier import recategorize
            print("🔄 بازسازی دسته‌ها و گراف...")
            recategorize(kb)
            n, e = Graph().build_from_kb(kb)
            s = Graph().stats()
            print(f"✓ {s['entities']} موجودیت، {s['resources']} منبع، "
                  f"{s['edges']} یال، {s['cooc']} co-occurrence")
            return

        if cmd == "graph-related":
            from graph import Graph
            if len(sys.argv) < 3:
                print("استفاده: graph-related <entity>"); return
            node = sys.argv[2]
            print(f"\n🔗 مرتبط‌های '{node}':\n")
            rels = Graph().related(node)
            if not rels:
                print(f"  (چیزی یافت نشد — ابتدا rebuild بزن)")
            for other, w in rels:
                print(f"  {other:30s} وزن {w}")
            return

        if cmd == "rebuild":
            from graph import Graph
            from classifier import recategorize
            print("🔄 بازسازی...")
            recategorize(kb)
            n, e = Graph().build_from_kb(kb)
            s = Graph().stats()
            print(f"✓ {s['entities']} موجودیت، {s['resources']} منبع، {s['edges']} یال، {s['cooc']} cooc")
            return

        if cmd == "graph-related":
            from graph import Graph
            if len(sys.argv) < 3:
                print("استفاده: graph-related <entity>"); return
            node = sys.argv[2]
            print(f"\n🔗 مرتبط‌های '{node}':\n")
            for other, w in Graph().related(node):
                print(f"  {other:30s} وزن {w}")
            return

        if cmd == "agents":
            from agents import Orchestrator
            orch = Orchestrator()
            print("🎭 اجرای چهار ایجنت...\n")
            r = orch.run_cycle(kb, evo)
            print(f"  🏹 Hunter: {len(r['hunter']['new_queries'])} کوئری جدید")
            print(f"  ⚖️  Judge: {r['judge']['low_quality']} ضعیف")
            print(f"  📚 Archivist: {r['archivist']['nodes']} نود، "
                  f"{r['archivist']['edges']} یال")
            print(f"  🔍 Critic: {r['critic']['total']} منبع")
            return

        if cmd == "agents-report":
            from agents import Orchestrator
            Orchestrator().report(); return

        if cmd == "graph-build":
            from graph import Graph
            g = Graph()
            n, e = g.build_from_kb(kb)
            print(f"✓ گراف ساخته شد: {n} نود، {e} یال")
            print(f"  فایل: {Path.home() / 'evoscanner' / 'graph.json'}")
            return

        if cmd == "graph-stats":
            from graph import Graph
            s = Graph().stats()
            print(f"\n🕸  گراف دانش:")
            print(f"  نودها: {s['entities']} موجودیت + {s['resources']} منبع")
            print(f"  یال‌ها: {s['edges']}")
            return

        if cmd == "graph-top":
            from graph import Graph
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            g = Graph()
            print(f"\n🔝 {n} موجودیت برتر:\n")
            for e, c in g.top_entities(n):
                bar = "█" * min(c, 40)
                print(f"  {e:25s} {c:4d}  {bar}")
            return

        if cmd == "graph-neighbors":
            from graph import Graph
            if len(sys.argv) < 3:
                print("استفاده: graph-neighbors <entity>")
                return
            node = sys.argv[2]
            g = Graph()
            print(f"\n🕸  همسایه‌های '{node}':\n")
            for nb, w, d in g.neighbors(node):
                arrow = "→" if d == "out" else "←"
                title = ""
                if nb.startswith("R:"):
                    t = g.data["nodes"].get(nb, {}).get("title", "")
                    title = f" ({t[:50]})"
                print(f"  {arrow} {nb:35s} وزن {w}{title}")
            return

        if cmd == "graph-path":
            from graph import Graph
            if len(sys.argv) < 4:
                print("استفاده: graph-path <start> <end>")
                return
            a, b = sys.argv[2], sys.argv[3]
            g = Graph()
            p = g.path(a, b)
            if p:
                print(f"\n🛤  مسیر {a} ← {b}:\n")
                print("  " + " → ".join(p))
            else:
                print(f"✗ مسیری بین {a} و {b} یافت نشد")
            return

        if cmd == "reclassify":
            from classifier import recategorize
            recategorize(kb); return

        if cmd == "export":
            from exporter import export_all
            export_all(kb); return

        if cmd == "export-json":
            from exporter import to_json
            to_json(kb); return

        if cmd == "export-csv":
            from exporter import to_csv
            to_csv(kb); return

        if cmd == "export-md":
            from exporter import to_markdown
            to_markdown(kb); return

        if cmd == "selfmod":
            from selfmod import SelfMod
            sm = SelfMod()
            action = sys.argv[2] if len(sys.argv) > 2 else "report"
            if action == "report":
                sm.report()
            elif action == "queries":
                sm.propose_queries(kb)
            elif action == "health":
                sm.optimize_health()
            elif action == "rollback":
                sm.rollback()
            elif action == "history":
                sm.history()
            elif action == "all":
                sm.report()
                sm.propose_queries(kb)
                sm.optimize_health()
            return

        if cmd == "suggest":
            from suggest import suggest
            suggest(kb, top_n=5); return

        if cmd == "path":
            from autopath import path as show_path
            topic = sys.argv[2] if len(sys.argv) > 2 else "asyncio"
            show_path(kb, topic); return

        if cmd == "web":
            from webui import serve
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
            serve(kb, evo, port); return

        if cmd == "graphweb":
            from graph_web import serve
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
            serve(port); return

        if cmd == "explore":
            explore(kb, evo); return
        if cmd == "stats":
            show_stats(kb, evo); return
        if cmd == "search":
            term = sys.argv[2] if len(sys.argv) > 2 else "python"
            results = kb.search(term, 30)
            # امتیازدهی TF-IDF سبک
            import math
            N = max(kb.total(), 1)
            scored = []
            term_lower = term.lower()
            for src, title, url, score in results:
                tf = title.lower().count(term_lower)
                if tf == 0:
                    tf = 1
                # idf تقریبی
                idf = math.log(N / 10) if N > 10 else 1.0
                ranked = (tf * idf) + score
                scored.append((ranked, src, title, url))
            scored.sort(reverse=True)
            for rank, src, title, url in scored[:20]:
                print(f"[{src:15s}] {rank:.2f}  {title[:65]}")
                print(f"   {url}")
            return

        if cmd == "offline":
            print("🔌 حالت آفلاین — فقط داده‌های موجود")
            show_stats(kb, evo)
            print("\n📂 دسته‌بندی منابع:")
            for cat, cnt, avg in kb.categories_stats():
                print(f"  {cat:15s} {cnt:4d}  میانگین {avg:.2f}")
            print("\n🏆 برترین‌ها در هر دسته:")
            for cat, cnt, avg in kb.categories_stats()[:5]:
                print(f"\n  ── {cat} ──")
                for src, title, url, score in kb.by_category(cat, 3):
                    print(f"    [{src}] {title[:60]}")
            return

        if cmd == "categories":
            for cat, cnt, avg in kb.categories_stats():
                print(f"  {cat:15s} {cnt:4d}  میانگین {avg:.2f}")
            return

        if cmd == "cat":
            cat = sys.argv[2] if len(sys.argv) > 2 else "web"
            for src, title, url, score in kb.by_category(cat, 30):
                print(f"[{src:15s}] {score:.2f}  {title[:65]}")
                print(f"   {url}")
            return

        if cmd == "top":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
            rows = kb.conn.execute(
                """SELECT source, title, url, score, category
                   FROM resources ORDER BY score DESC LIMIT ?""", (n,)).fetchall()
            for src, title, url, score, cat in rows:
                print(f"[{src:15s}|{cat:10s}] {score:.2f}  {title[:55]}")
                print(f"   {url}")
            return

        if cmd == "health":
            print("وضعیت سلامت منابع:")
            for name, fails in health.summary():
                status = "✓" if fails < 3 else "✗ خاموش"
                print(f"  {status}  {name:15s} خطاها: {fails}")
            return

        if cmd == "reset-health":
            health.data = {}
            health._save()
            print("✓ سلامت منابع ریست شد")
            return
        if cmd == "queries":
            for q in evo.state["active"]:
                print(f"  • {q}")
            return
        if cmd == "report":
            write_report(kb, evo); return
        if cmd == "run":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            try:
                for i in range(n):
                    one_cycle(kb, evo, evo.next_queries(6), health)
                    if i < n - 1:
                        print("  انتظار ۱۰s..."); time.sleep(10)
            except KeyboardInterrupt:
                print("\n⏸  متوقف شد — ذخیره وضعیت...")
            show_stats(kb, evo)
            write_report(kb, evo)
            return

    if len(sys.argv) > 1:
        print(f"❓ دستور ناشناخته: {sys.argv[1]}")
        print("   دستورات موجود:")
        print("   run | stats | search <term> | report | explore")
        print("   categories | cat <cat> | top <n> | suggest | path <topic>")
        print("   agents | agents-report | rebuild | export | reclassify")
        print("   graph-stats | graph-top <n> | graph-related <entity>")
        print("   graph-neighbors <entity> | graph-path <a> <b> | web")
        return
    one_cycle(kb, evo, evo.next_queries(6), health)
    show_stats(kb, evo)


if __name__ == "__main__":
    main()
