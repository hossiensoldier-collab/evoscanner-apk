"""استخراج دانش: تکنیک، مفهوم، قطعه کد، سختی"""
import json, re, sqlite3
from datetime import datetime
from pathlib import Path

DB = Path.home() / "evoscanner" / "knowledge.db"

# سطح سختی بر اساس کلمات
DIFFICULTY = {
    "beginner": [
        "introduction", "getting started", "basics", "hello world",
        "first", "beginner", "tutorial", "learn", "simple",
        "introduction to", "quickstart", "primer",
    ],
    "intermediate": [
        "guide", "how to", "advanced", "pattern", "practice",
        "intermediate", "example", "walkthrough",
    ],
    "advanced": [
        "optimization", "performance", "internals", "deep dive",
        "architecture", "production", "concurrency", "asynchronous",
        "compiler", "gc", "memory", "profiling",
    ],
    "specialist": [
        "research", "paper", "theorem", "mathematical", "algorithmic",
        "gpu", "shader", "opengl", "vulkan", "kernel", "numa",
        "cache coherence", "parallel", "distributed",
    ],
}


def classify_difficulty(text, title=""):
    t = (title + " " + text).lower()
    scores = {k: sum(1 for w in words if w in t)
              for k, words in DIFFICULTY.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "intermediate"


# ─── استخراج کد ───
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n([\s\S]*?)```", re.M)


def extract_code(text):
    out = []
    for m in CODE_BLOCK.finditer(text or ""):
        code = m.group(1).strip()
        if 20 < len(code) < 3000:
            out.append(code)
    return out


# ─── استخراج تکنیک ───
TECH_PATTERNS = [
    (r"(?:use|using)\s+([a-z_]{3,30})\s+(?:to|for)\s+([a-z_ ]{5,60})", "uses"),
    (r"(?:you can|you should|we recommend)\s+([a-z_ ]{5,80})", "recommend"),
    (r"(?:method|technique|pattern|approach):\s*([A-Za-z][A-Za-z _-]{3,40})", "named"),
    (r"([A-Z][a-z]+(?:[A-Z][a-z]+)+)\s+(?:pattern|technique|approach)", "camel"),
]


def extract_techniques(text, title=""):
    if not text:
        return []
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", text)
    found = set()
    for pat, kind in TECH_PATTERNS:
        for m in re.finditer(pat, text):
            g = m.groups()
            if kind == "camel":
                found.add((g[0], "pattern"))
            elif kind == "named":
                found.add((g[0].strip(), "named"))
            else:
                found.add((g[0].strip(), kind))
    return list(found)[:15]


# ─── استخراج وابستگی ───
DEP_PAT = re.compile(r"(?:pip\s+install|from|import)\s+([a-z][a-z0-9_-]{2,30})")
STOP = {"python", "the", "and", "for", "you", "this", "that", "with",
        "import", "from", "pip", "install"}


def extract_deps(text):
    if not text:
        return []
    return list({m.lower() for m in DEP_PAT.findall(text)
                 if m.lower() not in STOP})[:20]


# ─── استخراج مفهوم ───
CONCEPT_PAT = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:is|are|refers to|means)\s+"
    r"([a-z][^.!?]{15,200})", re.M)


def extract_concepts(text):
    if not text:
        return []
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    out = []
    for m in CONCEPT_PAT.finditer(text):
        name = m.group(1).strip()
        desc = m.group(2).strip()
        if 3 < len(name) < 40 and 20 < len(desc) < 250:
            out.append((name, desc))
    return out[:10]


# ─── ذخیره در پایگاه ───
def store_all(kb, source_hash, source_url, title, content):
    conn = kb.conn
    ts = datetime.now().isoformat()

    diff = classify_difficulty(content, title)
    deps = extract_deps(content)
    codes = extract_code(content)
    techs = extract_techniques(content, title)
    concepts = extract_concepts(content)

    # تکنیک‌ها
    tech_n = 0
    for name, kind in techs:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO techniques"
                "(name,category,description,source_hash,source_url,difficulty,prerequisites,extracted_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (name[:80], kind, "", source_hash, source_url,
                 diff, ",".join(deps[:5]), ts))
            tech_n += 1
        except Exception:
            pass

    # مفاهیم
    concept_n = 0
    for name, desc in concepts:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO concepts(name,description,category,difficulty,source_hash)"
                " VALUES(?,?,?,?,?)",
                (name[:60], desc, "auto", diff, source_hash))
            concept_n += 1
        except Exception:
            pass

    # کد
    code_n = 0
    for code in codes:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO snippets"
                "(source_hash,source_url,lang,purpose,code,lines,extracted_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (source_hash, source_url, "python", title[:100],
                 code[:3000], code.count("\n"), ts))
            code_n += 1
        except Exception:
            pass

    conn.commit()
    return {
        "difficulty": diff,
        "deps": deps,
        "techniques": tech_n,
        "concepts": concept_n,
        "snippets": code_n,
    }


def extract_all(kb, limit=500):
    """استخراج دانش از منابع گیت‌هاب"""
    rows = kb.conn.execute(
        "SELECT hash, url, title, content FROM resources "
        "WHERE source IN ('github','pypi','awesome','paperswithcode') "
        "AND length(COALESCE(content,'')) > 200 LIMIT ?", (limit,)
    ).fetchall()
    print(f"📖 استخراج از {len(rows)} منبع...")
    total = {"techniques": 0, "concepts": 0, "snippets": 0}
    for h, url, title, content in rows:
        r = store_all(kb, h, url, title, content or "")
        for k in total:
            total[k] += r[k]
    print(f"✓ تکنیک: {total['techniques']} | "
          f"مفهوم: {total['concepts']} | کد: {total['snippets']}")
    return total


if __name__ == "__main__":
    from evoscanner_v2 import KB
    kb = KB()
    extract_all(kb)
