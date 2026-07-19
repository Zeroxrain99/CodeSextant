"""S1 驗證截圖：v3-stunning.html 的 overview→飛入近 hub + 焦點 degree 驗證 + render-on-demand。"""
import functools
import http.server
import os
import shutil
import socketserver
import sys
import threading
import traceback
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = r"E:\Temp\cs_poc_c"
os.makedirs(SERVE, exist_ok=True)
for fn in ["v3-stunning.html", "graph-common.js", "graph_real.json", "graph_synth.json",
           "graph_cs_v3_tidy.json"]:   # 新預設圖（連續閘 + 分離測試）
    src = os.path.join(HERE, fn)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(SERVE, fn))

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SERVE)
httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
_probe = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v3-stunning.html", timeout=5).read(400).decode("utf-8", "replace")
assert "CodeSextant" in _probe, "server self-check 失敗"
print(f"http server :{PORT} self-check OK")


def main():
    with sync_playwright() as p:
        # 無頭（不開真視窗干擾 user）：WebGPU 在 headless 需 flags + SwiftShader 軟體後備
        browser = p.chromium.launch(
            headless=True,
            args=["--enable-unsafe-webgpu", "--enable-features=Vulkan",
                  "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--use-angle=swiftshader"],
        )
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        page.on("response", lambda r: logs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
        page.goto(f"http://127.0.0.1:{PORT}/v3-stunning.html", wait_until="load", timeout=30000)
        try:
            page.wait_for_function("window.__ready===true || window.__error", timeout=45000)
        except Exception as e:
            logs.append(f"wait __ready: {e}")
        err = page.evaluate("window.__error || null")
        print("__error =", err)
        # 1. overview 階段（morph 完成全貌、尚未飛入）
        page.screenshot(path=os.path.join(HERE, "shot-v3-overview.png"))
        focus = page.evaluate("window.__focus || null")
        print("window.__focus =", focus)
        # 2. 等飛入觸發 + 完成 → 近 hub
        try:
            page.wait_for_function("window.__introFlew===true", timeout=15000)
        except Exception as e:
            logs.append(f"wait introFlew: {e}")
        page.wait_for_timeout(1900)   # 飛入 1400ms + buffer
        page.screenshot(path=os.path.join(HERE, "shot-v3-near.png"))
        stat1 = page.evaluate("document.getElementById('stat').textContent")
        print("stat(飛入後) =", stat1)
        # 3. render-on-demand：再閒置 1.5s 看 fps（應掉到低/0）
        page.wait_for_timeout(1500)
        print("stat(閒置後) =", page.evaluate("document.getElementById('stat').textContent"))
        # 4. S2 雙擊兩段式：第一次雙擊 hub → fit 焦點+鄰居（看連線）
        hub = page.evaluate("window.__focusHub()")
        page.evaluate(f"window.__dblclick({hub})")
        page.wait_for_timeout(1100)
        page.screenshot(path=os.path.join(HERE, "shot-v3-dbl1-fit.png"))
        print("dbl1(fit鄰居) selected =", page.evaluate("document.getElementById('pn').textContent"))
        # 5. 對同節點再雙擊 → 貼單點最近（兩段式第二段）
        page.evaluate(f"window.__dblclick({hub})")
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(HERE, "shot-v3-dbl2-nearest.png"))
        print("dbl2(顯微鏡貼單點) pf =", page.evaluate("document.getElementById('pf').textContent"),
              "| camDist =", page.evaluate("window.__camDist()"))
        # 6. S3 五檔語義縮放（overview→far→mid→near→micro）各截圖 + 相機距離
        for tier in ["overview", "far", "mid", "near", "micro"]:
            page.evaluate(f"window.__setTier('{tier}')")
            page.wait_for_timeout(3200)
            page.screenshot(path=os.path.join(HERE, f"shot-v3-tier-{tier}.png"))
            print(f"tier {tier}: camDist =", page.evaluate("window.__camDist()"))
        if logs:
            print(f"console/err ({len(logs)}):")
            for l in logs[:30]:
                print("  " + l)
        browser.close()
    httpd.shutdown()
    print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        httpd.shutdown()
