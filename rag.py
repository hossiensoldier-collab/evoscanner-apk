"""RAG محلی — BM25 + جمله‌یابی"""
import math, re
from collections import Counter

STOP = set("the a an and or of in on to for with is are was were be been "
           "this that it as at by if not my we you can will have has had "
           "do does did but from".split())
TOKEN = re.compile(r'[a-zA-Z_][a-zA-Z0-9_\-]{1,30}')

def tokens(text):
    return [t.lower() for t in TOKEN.findall(text or "")
            if t.lower() not in STOP and len(t) > 2]

def sent_split(text):
    if not text: return []
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]+`', ' ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    return [p.strip() for p in parts if 40 < len(p.strip()) < 400]

def bm25_score(q_tokens, doc_tokens, avg_len, k1=1.5, b=0.75):
    if not doc_tokens: return 0.0
    dl = len(doc_tokens); tf = Counter(doc_tokens); score = 0.0
    for q in set(q_tokens):
        f = tf.get(q, 0)
        if f == 0: continue
        idf = math.log(1 + 1 / (f / dl + 0.5))
        score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avg_len))
    return score

def ask(kb, question, top_n=5):
    q_tokens = tokens(question)
    if not q_tokens:
        print("  ✗ سؤال نامعتبر"); return
    rows = kb.conn.execute(
        "SELECT hash, title, url, source, content, category FROM resources "
        "WHERE content IS NOT NULL AND length(content) > 200").fetchall()
    all_sents = []
    for h, title, url, source, content, cat in rows:
        for s in sent_split(content):
            all_sents.append({"text": s, "title": title, "url": url,
                "source": source, "category": cat, "tokens": tokens(s)})
    if not all_sents:
        print("  ✗ محتوایی نیست (اول enrich بزن)"); return
    avg_len = sum(len(s["tokens"]) for s in all_sents) / len(all_sents)
    for s in all_sents:
        s["score"] = bm25_score(q_tokens, s["tokens"], avg_len)
    all_sents.sort(key=lambda x: -x["score"])
    top = [s for s in all_sents[:top_n * 3] if s["score"] > 0]
    print(f"\n🔍 سؤال: {question}")
    print(f"   {len(q_tokens)} کلمه کلیدی | {len(all_sents)} جمله بررسی شد")
    print("─" * 60)
    seen = set(); n = 0
    for s in top:
        if s["url"] in seen: continue
        seen.add(s["url"]); n += 1
        print(f"\n📖 [{n}] {s['title'][:55]}")
        print(f"   {s['text'][:400]}")
        print(f"   ── {s['url']}")
        print(f"   امتیاز: {s['score']:.2f} | دسته: {s['category']}")
        if n >= top_n: break
    if n == 0:
        print("  ✗ پاسخ مرتبطی یافت نشد")
