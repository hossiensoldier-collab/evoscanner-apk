"""Knowledge Graph — با whitelist پکیج + category hub"""
import json, re
from collections import defaultdict
from pathlib import Path

BASE = Path.home() / "evoscanner"
GRAPH = BASE / "graph.json"

# ── whitelist پکیج‌های معروف پایتون (۲۰۰+) ──
PKGS = {
    # web
    "fastapi","flask","django","starlette","sanic","tornado","aiohttp",
    "httpx","requests","urllib3","uvicorn","gunicorn","hypercorn",
    "quart","litestar","reflex","solara","streamlit","gradio","dash",
    # async
    "asyncio","anyio","trio","curio","aiofiles","aioredis","asyncpg",
    "aiomysql","motor","aio-pika","websockets",
    # data
    "numpy","pandas","polars","duckdb","pyarrow","dask","vaex",
    "modin","cudf","pandasql",
    # ml/ai
    "torch","pytorch","tensorflow","keras","jax","flax","scikit-learn",
    "sklearn","xgboost","lightgbm","catboost","transformers",
    "sentence-transformers","langchain","llama-index","haystack",
    "huggingface","datasets","tokenizers","accelerate","peft",
    "diffusers","onnx","onnxruntime","mlflow","optuna","ray",
    "pydantic","pydantic-ai","instructor","openai","anthropic",
    "groq","ollama","vllm","llama-cpp-python","ctransformers",
    # testing
    "pytest","unittest","nose","hypothesis","tox","nox","behave",
    "robotframework","selenium","playwright","pyppeteer","locust",
    "pytest-asyncio","pytest-cov","pytest-mock","factory-boy","faker",
    # web scraping/parsing
    "beautifulsoup4","bs4","lxml","scrapy","scrapling","pyquery",
    "html5lib","xmltodict","regex","parsimonious","pyparsing","ply",
    "antlr4-python3-runtime","click","typer","argparse","docopt",
    # security
    "cryptography","pyjwt","passlib","bcrypt","pyopenssl","bandit",
    "safety","pip-audit","pacu","sqlmap","scapy","impacket",
    # devops
    "docker","kubernetes","ansible","fabric","paramiko","boto3",
    "google-cloud","azure-sdk","invoke","honcho","supervisor",
    # database
    "sqlalchemy","alembic","peewee","pony","tortoise-orm","redis",
    "pymongo","psycopg2","psycopg","asyncpg","aiosqlite","tinydb",
    # cli/tui
    "rich","textual","click","typer","colorama","tqdm","alive-progress",
    "prompt-toolkit","questionary","pytermgui","pyfiglet",
    # perf
    "numba","cython","pybind11","cffi","pypy","mypyc","scalene",
    "py-spy","memory-profiler","line-profiler","pyinstrument",
    # utils
    "pydantic","attrs","dataclasses-json","marshmallow","orjson",
    "ujson","msgpack","toml","tomli","pyyaml","ruamel-yaml","jsonschema",
    "python-dateutil","pendulum","arrow","pytz","whenever",
    "loguru","structlog","sentry-sdk","opentelemetry",
    "python-dotenv","dynaconf","environs","pydantic-settings",
    # typing
    "mypy","pyright","pytype","beartype","typeguard","typing-extensions",
    # packaging
    "poetry","hatch","flit","setuptools","wheel","build","twine",
    "pip","pipenv","virtualenv","uv","pdm",
    # git
    "gitpython","dulwich","pygit2","pre-commit","commitizen",
    # image/video
    "pillow","opencv-python","imageio","scikit-image","moviepy",
    "ffmpeg-python","av","wand",
    # audio
    "librosa","soundfile","pydub","pyaudio","speechrecognition",
    # jupyter
    "jupyter","ipython","notebook","jupyterlab","ipykernel","papermill",
    # graph
    "networkx","igraph","graph-tool","pyvis","plotly","bokeh","altair",
    # viz
    "matplotlib","seaborn","plotly","bokeh","altair","holoviews",
    "pygal","dash","panel","streamlit",
    # bot
    "python-telegram-bot","aiogram","discord.py","slack-sdk",
    "slack-bolt","twilio","telethon","pyrogram",
    # web3
    "web3","eth-brownie","solcx",
}

PKGS = PKGS | {p.lower() for p in list(PKGS)}

PAT_PIP      = re.compile(r'pip\s+(?:install|3\s+install)\s+([a-zA-Z][a-zA-Z0-9_\-]{1,40})', re.I)
PAT_BACKTICK = re.compile(r'`([a-zA-Z][a-zA-Z0-9_\-]{2,30})`')

STOP = {
    "build", "pip", "click", "setup", "wheel", "core", "user",
    "make", "version", "docs", "test", "tests", "lib",
    "python","the","and","for","with","from","import","this","that",
    "you","your","can","will","not","but","use","using","get","set",
    "code","test","data","file","name","main","read","write","run",
}


def extract_entities(text):
    """استخراج موجودیت‌ها: پکیج‌های whitelist + pip + backtick"""
    if not text:
        return set()
    tl = text.lower()
    ents = set()

    # ۱. پکیج‌های whitelist (سریع‌ترین راه)
    for pkg in PKGS:
        if len(pkg) < 4:
            continue
        # مرز کلمه
        if re.search(r'\b' + re.escape(pkg) + r'\b', tl):
            ents.add(pkg)

    # ۲. pip install
    for m in PAT_PIP.findall(text):
        m = m.lower().strip()
        if m not in STOP and len(m) >= 3:
            ents.add(m)

    # ۳. backtick (فقط اگر به‌نظر پکیج باشد)
    for m in PAT_BACKTICK.findall(text):
        m = m.lower().strip()
        if 3 <= len(m) <= 30 and m not in STOP and re.match(r'^[a-z][a-z0-9_\-]+$', m):
            ents.add(m)

    return ents


def repo_to_pkg(full_name):
    if not full_name:
        return None
    m = re.match(r'^[a-zA-Z0-9_\-]+/([a-zA-Z0-9_.\-]+)$', full_name.strip())
    if m:
        return m.group(1).lower()
    return None


class Graph:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if GRAPH.exists():
            try:
                return json.loads(GRAPH.read_text())
            except Exception:
                pass
        return {"nodes": {}, "edges": {}, "cooc": {}}

    def save(self):
        GRAPH.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def add_resource(self, h, title, content, source="", category="other"):
        nodes = self.data["nodes"]
        edges = self.data["edges"]
        cooc = self.data.setdefault("cooc", {})
        rid = f"R:{h}"

        # استخراج موجودیت‌ها
        text = (title or "") + "\n" + (content or "")
        ents = extract_entities(text)

        # افزودن نام پکیج از repo
        if source == "github" and title:
            pkg = repo_to_pkg(title)
            if pkg and len(pkg) >= 3:
                ents.add(pkg)

        # افزودن دسته به‌عنوان hub (به‌جز other)
        cat_hub = f"cat:{category}" if category != "other" else None
        if cat_hub:
            ents.add(cat_hub)

        # نود منبع
        nodes[rid] = {
            "type": "resource",
            "title": title or "",
            "source": source,
            "category": category,
            "entities": sorted(ents),
        }

        # نود + یال
        for e in ents:
            if e not in nodes:
                nodes[e] = {"type": "entity", "count": 0, "cats": {}}
            nodes[e]["count"] = nodes[e].get("count", 0) + 1
            cats = nodes[e].setdefault("cats", {})
            cats[category] = cats.get(category, 0) + 1
            key = f"{e}\u2192{rid}"
            edges[key] = edges.get(key, 0) + 1

        # یال موجودیت → cat_hub (پل بین منابع هم‌دسته)
        if cat_hub:
            for e in ents:
                if e.startswith("cat:"):
                    continue
                key2 = f"{e}\u2192{cat_hub}"
                edges[key2] = edges.get(key2, 0) + 1

        # co-occurrence بین موجودیت‌ها + با cat_hub
        real_ents = sorted(e for e in ents if not e.startswith("cat:"))
        for i, a in enumerate(real_ents):
            for b in real_ents[i+1:]:
                k = f"{a}|{b}" if a < b else f"{b}|{a}"
                cooc[k] = cooc.get(k, 0) + 1
            # موجودیت ↔ cat_hub
            if cat_hub:
                k2 = f"{a}|{cat_hub}" if a < cat_hub else f"{cat_hub}|{a}"
                cooc[k2] = cooc.get(k2, 0) + 1

    def build_from_kb(self, kb):
        self.data = {"nodes": {}, "edges": {}, "cooc": {}}
        rows = kb.conn.execute(
            "SELECT hash, title, content, source, category FROM resources"
        ).fetchall()
        for h, t, c, s, cat in rows:
            self.add_resource(h, t, c, s or "", cat or "other")
        self.save()
        return len(self.data["nodes"]), len(self.data["edges"])

    def neighbors(self, node, limit=20):
        node = node.lower()
        out = []
        for key, w in self.data["edges"].items():
            a, b = key.split("\u2192", 1)
            if a == node:
                out.append((b, w, "out"))
            elif b == node:
                out.append((a, w, "in"))
        out.sort(key=lambda x: -x[1])
        return out[:limit]

    def top_entities(self, limit=20, include_cats=False):
        ents = []
        for k, v in self.data["nodes"].items():
            if v.get("type") != "entity":
                continue
            if not include_cats and k.startswith("cat:"):
                continue
            ents.append((k, v.get("count", 0)))
        ents.sort(key=lambda x: -x[1])
        return ents[:limit]

    def related(self, entity, limit=15, include_cats=False):
        entity = entity.lower()
        rel = []
        for k, w in self.data.get("cooc", {}).items():
            a, b = k.split("|", 1)
            if a == entity:
                rel.append((b, w))
            elif b == entity:
                rel.append((a, w))
        if not include_cats:
            rel = [(n, w) for n, w in rel if not n.startswith("cat:")]
        rel.sort(key=lambda x: -x[1])
        return rel[:limit]

    def category_peers(self, entity, limit=20):
        """پکیج‌های هم‌دسته با این موجودیت"""
        entity = entity.lower()
        nodes = self.data["nodes"]
        # پیدا کردن دسته‌های این موجودیت
        cats = []
        if entity in nodes:
            cats = list(nodes[entity].get("cats", {}).keys())
        if not cats:
            return []
        # پیدا کردن سایر پکیج‌های همان دسته
        peers = {}
        for n, v in nodes.items():
            if v.get("type") != "entity" or n.startswith("cat:") or n == entity:
                continue
            for c in cats:
                if v.get("cats", {}).get(c):
                    peers[n] = peers.get(n, 0) + v["cats"][c]
        out = sorted(peers.items(), key=lambda x: -x[1])[:limit]
        return out

    def path(self, start, end, max_depth=5):
        from collections import deque
        start, end = start.lower(), end.lower()
        adj = defaultdict(set)
        for key in self.data["edges"]:
            a, b = key.split("\u2192", 1)
            adj[a].add(b); adj[b].add(a)
        for k in self.data.get("cooc", {}):
            a, b = k.split("|", 1)
            adj[a].add(b); adj[b].add(a)
        q = deque([(start, [start])])
        seen = {start}
        while q:
            node, p = q.popleft()
            if node == end:
                return p
            if len(p) > max_depth:
                continue
            for nb in adj[node]:
                if nb not in seen:
                    seen.add(nb)
                    q.append((nb, p + [nb]))
        return None

    def stats(self):
        nodes = self.data["nodes"]
        ents = sum(1 for v in nodes.values() if v.get("type") == "entity")
        res = sum(1 for v in nodes.values() if v.get("type") == "resource")
        cooc = len(self.data.get("cooc", {}))
        return {"entities": ents, "resources": res,
                "edges": len(self.data["edges"]), "cooc": cooc}

