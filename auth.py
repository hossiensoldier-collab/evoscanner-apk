"""مدیریت امن توکن GitHub با prompt داخل برنامه"""
import json
import os
import urllib.request
from pathlib import Path

BASE = Path.home() / "evoscanner"
ENV_FILE = BASE / ".env"
META_FILE = BASE / ".auth.json"


def _read_env_token():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""


def get_token():
    """اولویت: env → فایل .env"""
    t = os.environ.get("GITHUB_TOKEN", "")
    if t:
        return t
    return _read_env_token()


def save_token(token):
    """ذخیره در .env با chmod 600"""
    token = token.strip()
    ENV_FILE.write_text(f"GITHUB_TOKEN={token}\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass


def delete_token():
    if ENV_FILE.exists():
        try:
            ENV_FILE.unlink()
        except Exception:
            pass
    if META_FILE.exists():
        try:
            META_FILE.unlink()
        except Exception:
            pass


def verify_token(token, timeout=10):
    """چک می‌کند توکن معتبر است"""
    if not token or len(token) < 20:
        return False, "توکن خیلی کوتاه است"
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": "token " + token,
            "User-Agent": "EvoScanner-AuthCheck",
            "Accept": "application/vnd.github+json",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
            meta = {
                "login": data.get("login", "?"),
                "name": data.get("name", ""),
                "limit": r.headers.get("X-RateLimit-Limit", "?"),
                "remaining": r.headers.get("X-RateLimit-Remaining", "?"),
                "reset": r.headers.get("X-RateLimit-Reset", "?"),
            }
            META_FILE.write_text(json.dumps(meta, indent=2))
            return True, meta
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "توکن نامعتبر (401 Unauthorized)"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def get_meta():
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except Exception:
            pass
    return {}


def prompt_for_token(force=False):
    """
    از کاربر توکن می‌پرسد.
    اگر از قبل هست و force=False، همان را برمی‌گرداند.
    """
    existing = get_token()
    if existing and not force:
        return existing

    print()
    print("=" * 55)
    print("  GitHub Token — Baraye dastrasi be API")
    print("=" * 55)
    print()
    print("  Chera lazem ast?")
    print("    - Bedoone token: 60 darkhast dar saat")
    print("    - Ba token:      5000 darkhast dar saat")
    print()
    print("  Tariqe sakht:")
    print("    1. Bere be: https://github.com/settings/tokens/new")
    print("    2. Note: evoscanner")
    print("    3. Scope: public_repo (faghat hamim)")
    print("    4. Generate -> copy")
    print()
    print(f"  {chr(27)}[2mToken ro inja paste kon va Enter bezan{chr(27)}[0m")
    print(f"  {chr(27)}[2m(ya faqat Enter bezan baraye rad kardan){chr(27)}[0m")
    print()

    try:
        token = input("  token > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  cancel")
        return existing

    if not token:
        print("  rad shod — bedoone token edame midahim")
        return existing

    print("\n  verifing...")
    ok, info = verify_token(token)
    if not ok:
        print(f"  [XX] {info}")
        print("  token zakhire nashod")
        return existing

    save_token(token)
    print(f"  [OK] Valid — user: {info['login']}")
    print(f"       rate limit: {info['limit']}/h  "
          f"(remaining: {info['remaining']})")
    print(f"  [OK] Save shod dar .env")
    return token


def status():
    """نمایش وضعیت"""
    t = get_token()
    if not t:
        return {"has_token": False}
    ok, info = verify_token(t)
    if not ok:
        return {"has_token": True, "valid": False, "error": info}
    return {"has_token": True, "valid": True, "meta": info}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "set":
            prompt_for_token(force=True)
        elif sys.argv[1] == "delete":
            delete_token()
            print("حذف شد")
        elif sys.argv[1] == "status":
            print(json.dumps(status(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(status(), indent=2, ensure_ascii=False))
