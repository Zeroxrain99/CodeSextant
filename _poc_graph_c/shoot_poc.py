"""Phase0 PoC 截圖：spectral pure vs remap 兩版，各截 overview(全貌) + near(飛入)。"""
import functools
import http.server
import os
import shutil
import socketserver
import sys
import threading
import traceback

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = r"E:\Temp\cs_poc_c"
os.makedirs(SERVE, exist_ok=True)
for fn in ["v3-stunning.html", "graph-common.js", "graph_real.json",
           "graph_spectral_pure.json", "graph_spectral_remap.json"]:
    shutil.copy2(os.path.join(HERE, fn), os.path.join(SERVE, fn))

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SERVE)
httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
print(f"server :{PORT}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--enable-unsafe-webgpu", "--enable-features=Vulkan",
                  "--ignore-gpu-blocklist", "--use-angle=default"],
        )
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        logs = []
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        for tag, g in [("pure", "graph_spectral_pure.json"), ("remap", "graph_spectral_remap.json")]:
            page.goto(f"http://127.0.0.1:{PORT}/v3-stunning.html?g={g}", wait_until="load", timeout=30000)
            try:
                page.wait_for_function("window.__ready===true || window.__error", timeout=45000)
            except Exception as e:
                logs.append(f"[{tag}] wait ready: {e}")
            err = page.evaluate("window.__error || null")
            print(f"[{tag}] __error =", err)
            page.wait_for_timeout(2600)   # morph 聚合
            page.screenshot(path=os.path.join(HERE, f"poc-{tag}-overview.png"))
            try:
                page.wait_for_function("window.__introFlew===true", timeout=12000)
            except Exception as e:
                logs.append(f"[{tag}] introFlew: {e}")
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(HERE, f"poc-{tag}-near.png"))
            focus = page.evaluate("window.__focus || null")
            print(f"[{tag}] camDist =", page.evaluate("window.__camDist()"), "| focus =", focus)
        if logs:
            print("logs:", *logs[:20], sep="\n  ")
        browser.close()
    httpd.shutdown()
    print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        httpd.shutdown()
