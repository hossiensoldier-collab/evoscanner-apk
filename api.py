"""HTTP API برای ادیتورها — پورت 8081"""
import json, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path.home() / "evoscanner"
GRAPH = BASE / "graph.json"
DB = BASE / "knowledge.db"

import sqlite3


def get_kb():
    return sqlite3.connect(DB)


def _json_response(self, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)


# ── Endpointها ──

def ep_search(q, limit=10):
    """جستجوی منابع"""
    kb = get_kb()
    rows = kb.execute(
        """SELECT source, title, url, score, category FROM resources
           WHERE title LIKE ? OR content LIKE ?
           ORDER BY score DESC LIMIT ?""",
        (f"%{q}%", f"%{q}%", limit)
    ).fetchall()
    kb.close()
    return [{"source": s, "title": t, "url": u,
             "score": sc, "category": c} for s, t, u, sc, c in rows]


def ep_related(pkg, limit=15):
    """پکیج‌های مرتبط"""
    if not GRAPH.exists():
        return {"package": pkg, "related": [], "peers": []}
    g = json.loads(GRAPH.read_text())
    cooc = g.get("cooc", {})
    nodes = g.get("nodes", {})
    pkg = pkg.lower()

    rels = []
    for pair, w in cooc.items():
        a, b = pair.split("|", 1)
        if a.startswith("cat:") or b.startswith("cat:"):
            continue
        if a == pkg:
            rels.append((b, w))
        elif b == pkg:
            rels.append((a, w))
    rels.sort(key=lambda x: -x[1])

    info = nodes.get(pkg, {})
    cats = info.get("cats", {})
    peers = []
    if cats:
        main = max(cats, key=cats.get)
        for n, v in nodes.items():
            if v.get("type") != "entity" or n == pkg:
                continue
            if v.get("cats", {}).get(main):
                peers.append((n, v["cats"][main]))
        peers.sort(key=lambda x: -x[1])

    return {
        "package": pkg,
        "category": max(cats, key=cats.get) if cats else "other",
        "count": info.get("count", 0),
        "related": [{"name": n, "weight": w} for n, w in rels[:limit]],
        "peers": [{"name": n, "weight": w} for n, w in peers[:limit]],
    }


def ep_ask(q, top_n=3):
    """سؤال → پاسخ"""
    try:
        from rag import ask
        from evoscanner_v2 import KB
        kb_obj = KB()
        # می‌گیریم فقط نتایج
        result = []
        q_tokens = __import__("rag").tokens(q)
        rows = kb_obj.conn.execute(
            """SELECT title, url, content, category FROM resources
               WHERE content IS NOT NULL AND length(content) > 200"""
        ).fetchall()
        import re
        import math
        from collections import Counter
        # ساده: امتیاز on-the-fly
        from rag import sent_split, bm25_score
        all_sents = []
        for title, url, content, cat in rows:
            for s in sent_split(content):
                all_sents.append((s, title, url, cat))
        avg_len = 50
        scored = []
        for s, title, url, cat in all_sents:
            toks = __import__("rag").tokens(s)
            sc = bm25_score(q_tokens, toks, avg_len)
            if sc > 0:
                scored.append((sc, s[:400], title, url, cat))
        scored.sort(reverse=True)
        seen = set()
        for sc, text, title, url, cat in scored:
            if url in seen:
                continue
            seen.add(url)
            result.append({"text": text, "title": title,
                          "url": url, "category": cat, "score": round(sc, 2)})
            if len(result) >= top_n:
                break
        return {"question": q, "answers": result}
    except Exception as e:
        return {"question": q, "answers": [], "error": str(e)}


def ep_path(a, b):
    """مسیر در گراف"""
    if not GRAPH.exists():
        return {"path": None}
    g = json.loads(GRAPH.read_text())
    from collections import defaultdict, deque
    adj = defaultdict(set)
    for key in g.get("edges", {}):
        x, y = key.split("\u2192", 1)
        adj[x].add(y)
        adj[y].add(x)
    for k in g.get("cooc", {}):
        x, y = k.split("|", 1)
        adj[x].add(y)
        adj[y].add(x)
    a, b = a.lower(), b.lower()
    q = deque([(a, [a])])
    seen = {a}
    while q:
        n, p = q.popleft()
        if n == b:
            return {"path": p}
        if len(p) > 5:
            continue
        for nb in adj[n]:
            if nb not in seen:
                seen.add(nb)
                q.append((nb, p + [nb]))
    return {"path": None}


def ep_suggest(code):
    """پیشنهاد پکیج بر اساس کد"""
    import re
    imports = re.findall(r'^(?:import|from)\s+([a-z][a-z0-9_]+)', code, re.M)
    if not imports:
        return {"suggestions": []}
    if not GRAPH.exists():
        return {"suggestions": []}
    g = json.loads(GRAPH.read_text())
    cooc = g.get("cooc", {})
    seen = set()
    suggestions = []
    for pkg in set(imports):
        for pair, w in cooc.items():
            a, b = pair.split("|", 1)
            if a.startswith("cat:") or b.startswith("cat:"):
                continue
            if a == pkg and b not in seen and b not in imports:
                suggestions.append({"pkg": b, "for": pkg, "weight": w})
                seen.add(b)
            elif b == pkg and a not in seen and a not in imports:
                suggestions.append({"pkg": a, "for": pkg, "weight": w})
                seen.add(a)
    suggestions.sort(key=lambda x: -x["weight"])
    return {"suggestions": suggestions[:10]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)
        cmd = p.path.strip("/")

        if cmd in ("", "health"):
            self._json({"ok": True})
        elif cmd == "search":
            self._json(ep_search(qs.get("q", [""])[0],
                                 int(qs.get("limit", ["10"])[0])))
        elif cmd == "related":
            self._json(ep_related(qs.get("pkg", [""])[0]))
        elif cmd == "ask":
            self._json(ep_ask(qs.get("q", [""])[0],
                              int(qs.get("top", ["3"])[0])))
        elif cmd == "path":
            self._json(ep_path(qs.get("a", [""])[0], qs.get("b", [""])[0]))
        elif cmd == "suggest":
            self._json(ep_suggest(qs.get("code", [""])[0]))
        else:
            self.send_error(404)

    def do_POST(self):
        import urllib.parse
        p = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="ignore")
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if p.path == "/suggest":
            self._json(ep_suggest(data.get("code", "")))
        else:
            self.send_error(404)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port=8081):
    print(f"\n🔌 API سرور: http://localhost:{port}")
    print("   Endpoints:")
    print(f"     /search?q=<query>")
    print(f"     /related?pkg=<name>")
    print(f"     /ask?q=<question>")
    print(f"     /path?a=<x>&b=<y>")
    print(f"     /suggest (POST {{code:...}})")
    print("   Ctrl+C برای توقف\n")
    try:
        HTTPServer(("", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n⏸ متوقف شد")


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    serve(port)

