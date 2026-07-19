"""階段1 端到端 daemon 驗證：坑7 CSRF + 坑6 git freshness 走真 HTTP（非單元測試）。

對 port 8791 的 daemon 發真實 HTTP：health / status(lazy) / status?fresh=1 /
POST 帶各種 Origin，驗證硬化在真 daemon HTTP 層 work。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
PROJ = r"E:\ai-king\項目資料\CodeSextant"


def _get(path, origin=None):
    req = urllib.request.Request(BASE + path)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post(path, body, origin=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    print("=== 端到端 daemon HTTP 驗證（port 8791，真 HTTP 非單元測試）===")
    q = urllib.parse.quote(PROJ)

    c, h = _get("/health")
    print(f"[health] {c} service={h.get('service')} 就緒={h.get('就緒') or h.get('ready')}")

    c, s = _get(f"/status?project={q}")
    print(f"[status 預設] {c} git_stale in resp? {'git_stale' in s} "
          f"(應 False＝坑7-1 lazy 不 spawn git)")

    c, sf = _get(f"/status?project={q}&fresh=1")
    print(f"[status fresh=1] {c} git_stale={sf.get('git_stale')} "
          f"indexed_sha={str(sf.get('indexed_git_sha'))[:8]} "
          f"current_sha={str(sf.get('current_git_sha'))[:8]} (坑6 freshness)")

    c, _ = _post("/find_references", {"project": PROJ, "symbol": "_env_on"},
                 origin="http://127.0.0.1:8791")
    print(f"[POST 本機 Origin] {c} (應 200＝坑7 放行本機 loopback)")

    c, e = _post("/find_references", {"project": PROJ, "symbol": "_env_on"},
                 origin="http://evil.example.com")
    print(f"[POST 外部 Origin] {c} (應 403＝坑7 擋外部跨站) {str(e.get('error',''))[:36]}")

    c, _ = _post("/find_references", {"project": PROJ, "symbol": "_env_on"},
                 origin="https://tauri.localhost")
    print(f"[POST tauri.localhost] {c} (應 200＝坑7-2 Tauri v2 放行)")

    c, e = _post("/find_references", {"project": PROJ, "symbol": "_env_on"},
                 origin="http://127.0.0.1.evil.com")
    print(f"[POST 前綴繞過嘗試] {c} (應 403＝擋 127.0.0.1.evil.com 前綴繞過)")


if __name__ == "__main__":
    main()
