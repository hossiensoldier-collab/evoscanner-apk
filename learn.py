"""سیستم یادگیری: مسیر، آمار، چرخه خودکار"""
from datetime import datetime

DIFF_ORDER = ["beginner","intermediate","advanced","specialist"]
DIFF_FA = {"beginner":"مبتدی","intermediate":"متوسط",
           "advanced":"پیشرفته","specialist":"تخصصی"}


def build_path(kb, topic, max_per_level=8):
    conn = kb.conn

    # اگر موضوع graphics است، از کتابخانه‌های گرافیک استفاده کن
    keywords = [topic]
    if topic.lower() in ("graphics", "graphic", "visualization", "viz"):
        try:
            from graphics import GRAPHICS_LIBS
            keywords = list(GRAPHICS_LIBS.keys()) + ["image", "render",
                                                     "shader", "graphics"]
        except Exception:
            keywords = ["matplotlib", "opencv", "pygame", "plotly",
                        "pillow", "graphics"]

    # ساخت شرط OR برای همه کلمات
    clauses = " OR ".join(["title LIKE ? OR content LIKE ?"
                           for _ in keywords])
    params = []
    for k in keywords:
        params.append(f"%{k}%")
        params.append(f"%{k}%")

    rows = conn.execute(
        f"SELECT hash, url, title, source, content, score FROM resources "
        f"WHERE {clauses} ORDER BY score DESC LIMIT 300",
        params).fetchall()
    if not rows:
        return {"error": f"No resources for '{topic}'"}
    from extractor import classify_difficulty
    buckets = {k: [] for k in DIFF_ORDER}
    for h, url, title, source, content, score in rows:
        d = classify_difficulty(content or "", title or "")
        buckets[d].append({"hash":h,"url":url,"title":title,
                           "source":source,"score":score})
    for lvl in DIFF_ORDER:
        buckets[lvl].sort(key=lambda x: -(x["score"] or 0))
        buckets[lvl] = buckets[lvl][:max_per_level]
    step = 0
    for lvl in DIFF_ORDER:
        for it in buckets[lvl]:
            step += 1
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO learn_paths"
                    "(topic,level,step,title,description,resource_url,source_hash)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (topic, lvl, step, it["title"][:100],
                     f"منبع {it['source']}", it["url"], it["hash"]))
            except Exception: pass
    conn.commit()
    return {"topic":topic, "buckets":buckets, "total":step}


def show_path(kb, topic):
    r = build_path(kb, topic)
    if "error" in r:
        print(f"\n  ! {r['error']}"); return
    print(f"\n=== Path: {topic} ===\n")
    for lvl in DIFF_ORDER:
        items = r["buckets"][lvl]
        if not items: continue
        print(f"  [{DIFF_FA[lvl]}]  {len(items)}")
        for it in items[:6]:
            print(f"    * [{it['source']:12s}] {it['title'][:50]}")
            print(f"        {it['url']}")
        print()
    print(f"  کل: {r['total']} منبع")


def show_techniques(kb, category=None):
    conn = kb.conn
    if category:
        rows = conn.execute(
            "SELECT name,category,source_url,difficulty FROM techniques "
            "WHERE category=? OR name LIKE ? LIMIT 30",
            (category, f"%{category}%")).fetchall()
    else:
        rows = conn.execute(
            "SELECT name,category,source_url,difficulty FROM techniques "
            "LIMIT 40").fetchall()
    if not rows:
        print("  (خالی — اول 'extract')"); return
    print(f"\n=== Techniques ({len(rows)}) ===\n")
    for name, cat, url, diff in rows:
        print(f"  [{diff[:4]:4s}] {name[:40]:40s} ({cat})")


def show_snippets(kb, topic=None, limit=10):
    conn = kb.conn
    if topic:
        rows = conn.execute(
            "SELECT purpose,code,source_url FROM snippets "
            "WHERE purpose LIKE ? OR code LIKE ? LIMIT ?",
            (f"%{topic}%", f"%{topic}%", limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT purpose,code,source_url FROM snippets LIMIT ?",
            (limit,)).fetchall()
    if not rows:
        print("  (خالی)"); return
    for i, (purpose, code, url) in enumerate(rows, 1):
        print(f"\n--- [{i}] {purpose[:60]} ---")
        print(f"  {url}")
        for l in code.split("\n")[:8]:
            print(f"    {l}")
        if code.count("\n") > 8:
            print(f"    ... ({code.count(chr(10))-8} خط)")


def stats(kb):
    conn = kb.conn
    print("\n=== Learning Stats ===\n")
    for t in ("techniques","concepts","snippets","learn_paths","graphics_topics"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:18s} {n:5d}")
        except Exception: pass
    print("\n  Techniques by difficulty:")
    for diff, n in conn.execute(
        "SELECT difficulty, COUNT(*) FROM techniques "
        "GROUP BY difficulty ORDER BY COUNT(*) DESC").fetchall():
        print(f"    {diff:14s} {n}")


def auto_learn(kb, rounds=1):
    print(f"\n🧠 Learning cycle ({rounds})\n")
    from extractor import extract_all
    from graphics import extract_graphics_topics
    for i in range(rounds):
        print(f"--- round {i+1} ---")
        extract_all(kb, limit=300)
        n = extract_graphics_topics(kb)
        print(f"  graphics topics: {n}")
    stats(kb)


if __name__ == "__main__":
    import sys
    from evoscanner_v2 import KB
    kb = KB()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "extract": auto_learn(kb, 1)
        elif cmd == "path": show_path(kb, sys.argv[2] if len(sys.argv)>2 else "graphics")
        elif cmd == "tech": show_techniques(kb, sys.argv[2] if len(sys.argv)>2 else None)
        elif cmd == "snippet": show_snippets(kb, sys.argv[2] if len(sys.argv)>2 else None)
        elif cmd == "stats": stats(kb)
        elif cmd == "graphics":
            from graphics import graphics_report
            graphics_report(kb)
    else: stats(kb)

