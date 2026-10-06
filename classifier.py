"""دسته‌بندی هوشمند با وزن‌دهی عنوان و کلمه‌ی کامل"""
import re

# هر دسته: (کلمات عنوان با وزن ۳، کلمات محتوا با وزن ۱)
CATS = {
    "async": {
        "t": ["asyncio", "aiohttp", "anyio", "trio", "async"],
        "c": ["coroutine", "await", "concurrent", "event loop"],
    },
    "web": {
        "t": ["fastapi", "django", "flask", "starlette", "tornado",
              "httpx", "aiohttp", "sanic", "reflex", "solara"],
        "c": ["rest api", "web framework", "http server", "wsgi", "asgi"],
    },
    "ml-ai": {
        "t": ["transformers", "pytorch", "tensorflow", "scikit",
              "gradio", "langchain", "llm", "neural"],
        "c": ["machine learning", "deep learning", "neural network",
              "training", "inference", "embedding"],
    },
    "data": {
        "t": ["pandas", "numpy", "polars", "duckdb", "edgartools"],
        "c": ["dataframe", "data pipeline", "etl", "csv", "parquet"],
    },
    "testing": {
        "t": ["pytest", "hypothesis", "tox", "nox", "behave"],
        "c": ["unit test", "test framework", "coverage", "mock", "fixture"],
    },
    "performance": {
        "t": ["numba", "cython", "pytermgui", "sentry"],
        "c": ["benchmark", "profiler", "jit", "optimization", "latency"],
    },
    "typing": {
        "t": ["mypy", "pydantic", "beartype", "pyright"],
        "c": ["type hint", "type checking", "generic", "protocol"],
    },
    "patterns": {
        "t": ["dowhy", "injector"],
        "c": ["design pattern", "dependency injection", "architecture",
              "solid principle", "refactoring"],
    },
    "packaging": {
        "t": ["poetry", "uv", "hatch", "flit"],
        "c": ["pyproject", "wheel", "setuptools", "package manager"],
    },
    "parsing": {
        "t": ["beautifulsoup", "lxml", "scrapy", "playwright",
              "scrapling", "webskrap", "crawler"],
        "c": ["parser", "regex", "html parsing", "scraping"],
    },
    "security": {
        "t": ["bandit", "pacu", "pentestgpt", "cryptography",
              "oauth", "jwt"],
        "c": ["vulnerability", "penetration", "cve", "encryption",
              "authentication", "injection"],
    },
    "devops": {
        "t": ["docker", "kubernetes", "ansible"],
        "c": ["ci cd", "github actions", "deployment", "pipeline",
              "container", "orchestration"],
    },
    "bots": {
        "t": ["slack-sdk", "telegram", "discord"],
        "c": ["chatbot", "bot framework", "messaging"],
    },
}


def _count(text, word):
    """شمارش کلمه با مرز کلمه (جلوگیری از false positive)"""
    if " " in word:
        return text.count(word)
    return len(re.findall(r"\b" + re.escape(word) + r"\b", text))


def categorize(title, content="", tags=""):
    """امتیازدهی وزن‌دار: عنوان ۳، محتوا ۱، تگ ۲"""
    tl = (title or "").lower()
    cl = (content or "").lower()
    g = (tags or "").lower()

    scores = {}
    for cat, words in CATS.items():
        s = 0
        for w in words["t"]:
            s += _count(tl, w) * 3
        for w in words["c"]:
            s += _count(cl, w) * 1
        for w in words["t"] + words["c"]:
            s += _count(g, w) * 2
        if s > 0:
            scores[cat] = s

    if not scores:
        return "other"
    top = max(scores, key=scores.get)
    # اگر امتیاز خیلی ضعیف بود، بگذار other
    if scores[top] < 2:
        return "other"
    return top


def recategorize(kb):
    """دوباره دسته‌بندی همه منابع"""
    rows = kb.conn.execute(
        "SELECT hash, title, content, tags FROM resources"
    ).fetchall()
    n = 0
    for h, t, c, g in rows:
        new_cat = categorize(t or "", c or "", g or "")
        cur = kb.conn.execute(
            "SELECT category FROM resources WHERE hash=?", (h,)
        ).fetchone()
        if cur and cur[0] != new_cat:
            kb.conn.execute(
                "UPDATE resources SET category=? WHERE hash=?", (new_cat, h)
            )
            n += 1
    kb.conn.commit()
    print(f"  🔄 {n} منبع دوباره دسته‌بندی شد")
    return n

