"""功能 C PoC 截圖：起本地 http server + playwright 開兩個 PoC + 抓 console 錯誤 + 截圖。
WebGPU 需要 secure context(localhost OK) + GPU flag；headless=False 出真實 GPU 渲染。"""
import functools
import http.server
import os
import shutil
import socketserver
import sys
import threading
import traceback

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
# SimpleHTTPRequestHandler 在含中文的目錄(項目資料)serve 會 404(Windows ACP 路徑編碼)→ 複製到純 ASCII 臨時目錄 serve。
SERVE = r"E:\Temp\cs_poc_c"
os.makedirs(SERVE, exist_ok=True)
for fn in ["poc-a-webgl2.html", "poc-b-webgpu-tsl.html", "v2-stunning.html", "graph-common.js",
           "graph_real.json", "graph_synth.json"]:
    shutil.copy2(os.path.join(HERE, fn), os.path.join(SERVE, fn))
import urllib.request

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SERVE)
# ⛔ 不用 allow_reuse_address：Windows SO_REUSEADDR 會與占用者(殘留服務 PID4440 占 8799)共存、
# 請求被搶走回 404。用 port 0 讓 OS 分配保證空閒 port。
httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
# server 自檢：確認撈到的真是我的 PoC（排除 port 被占假冒）
_probe = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/poc-a-webgl2.html", timeout=5).read(400).decode("utf-8", "replace")
assert "CodeSextant" in _probe, "server self-check 失敗：撈到的不是我的 PoC（port 被占？）"
print(f"http server on :{PORT} (serve={SERVE}) self-check OK")


def shot(ctx, name, path, settle_ms):
    page = ctx.new_page()
    logs = []
    page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: logs.append(f"REQ-FAIL {r.url} :: {r.failure}"))
    page.on("response", lambda r: logs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    url = f"http://127.0.0.1:{PORT}/{path}"
    try:
        page.goto(url, wait_until="load", timeout=30000)
    except Exception as e:
        logs.append(f"goto fail: {e}")
    try:
        page.wait_for_function("window.__ready===true || window.__error", timeout=30000)
    except Exception as e:
        logs.append(f"wait __ready timeout: {e}")
    page.wait_for_timeout(settle_ms)
    err = None
    try:
        err = page.evaluate("window.__error || null")
        stat = page.evaluate("document.getElementById('stat') && document.getElementById('stat').textContent")
    except Exception as e:
        stat = f"(eval fail {e})"
    out = os.path.join(HERE, name)
    page.screenshot(path=out)
    print(f"\n=== {name} ===")
    print(f"  url={url}")
    print(f"  __error={err}")
    print(f"  stat={stat}")
    if logs:
        print(f"  console/pageerror ({len(logs)}):")
        for l in logs[:25]:
            print("    " + l)
    page.close()
    return err, stat


def shot_v2(ctx):
    page = ctx.new_page()
    logs = []
    page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
    page.on("response", lambda r: logs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
    url = f"http://127.0.0.1:{PORT}/v2-stunning.html"
    page.goto(url, wait_until="load", timeout=30000)
    try:
        page.wait_for_function("window.__ready===true || window.__error", timeout=45000)
    except Exception as e:
        logs.append(f"wait __ready timeout: {e}")
    page.wait_for_timeout(1200)
    err = page.evaluate("window.__error || null")
    page.screenshot(path=os.path.join(HERE, "shot-v2-overview.png"))
    print(f"\n=== v2 overview ===  __error={err}")
    print("  stat=", page.evaluate("document.getElementById('stat') && document.getElementById('stat').textContent"))
    try:
        name = page.evaluate("window.__selectTop ? window.__selectTop() : null")
        print("  selected top node =", name)
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(HERE, "shot-v2-selected.png"))
    except Exception as e:
        logs.append(f"select fail: {e}")
    if logs:
        print(f"  console/pageerror ({len(logs)}):")
        for l in logs[:30]:
            print("    " + l)
    page.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--enable-unsafe-webgpu", "--enable-features=Vulkan",
                  "--ignore-gpu-blocklist", "--use-angle=default"],
        )
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        try:
            shot_v2(ctx)
        finally:
            browser.close()
    httpd.shutdown()
    print("\nDONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        httpd.shutdown()
