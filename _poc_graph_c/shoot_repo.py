"""截某 repo 的 spectral pure/remap 兩版 overview+near。用法: python shoot_repo.py <name>"""
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

NAME = sys.argv[1] if len(sys.argv) > 1 else "sancio"
TAGS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["pure", "remap"]
HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = r"E:\Temp\cs_poc_c"
os.makedirs(SERVE, exist_ok=True)
for fn in ["v3-stunning.html", "graph-common.js"] + [f"graph_{NAME}_{t}.json" for t in TAGS]:
    shutil.copy2(os.path.join(HERE, fn), os.path.join(SERVE, fn))

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SERVE)
httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
print(f"server :{PORT} name={NAME}")


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
        for tag in TAGS:
            g = f"graph_{NAME}_{tag}.json"
            page.goto(f"http://127.0.0.1:{PORT}/v3-stunning.html?g={g}", wait_until="load", timeout=30000)
            try:
                page.wait_for_function("window.__ready===true || window.__error", timeout=60000)
            except Exception as e:
                logs.append(f"[{tag}] ready: {e}")
            print(f"[{NAME}/{tag}] __error =", page.evaluate("window.__error || null"))
            page.wait_for_timeout(2600)
            page.screenshot(path=os.path.join(HERE, f"poc-{NAME}-{tag}-overview.png"))
            try:
                page.wait_for_function("window.__introFlew===true", timeout=12000)
            except Exception as e:
                logs.append(f"[{tag}] introFlew: {e}")
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(HERE, f"poc-{NAME}-{tag}-near.png"))
            print(f"[{NAME}/{tag}] camDist =", page.evaluate("window.__camDist()"),
                  "| focus =", page.evaluate("window.__focus || null"))
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
