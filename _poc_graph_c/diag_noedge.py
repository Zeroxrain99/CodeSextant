"""決定性診斷：關掉連線只看節點點雲，判斷團塊是「佈局佈出來了、被線糊掉」還是「佈局本身就沒團塊」。
產 graph_<name>_noedge.json（edges=[]，座標不變）+ 截 overview。用法: python diag_noedge.py <name>"""
import functools
import http.server
import json
import os
import shutil
import socketserver
import sys
import threading
import traceback

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "sancio"
HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = r"E:\Temp\cs_poc_c"
os.makedirs(SERVE, exist_ok=True)

# 產 noedge 版（讀 remap，清空 edges，座標保留）
g = json.load(open(os.path.join(HERE, f"graph_{NAME}_gib.json"), encoding="utf-8"))
g["edges"] = []
noedge_name = f"graph_{NAME}_gibnoedge.json"
json.dump(g, open(os.path.join(SERVE, noedge_name), "w", encoding="utf-8"), ensure_ascii=False)
for fn in ["v3-stunning.html", "graph-common.js"]:
    shutil.copy2(os.path.join(HERE, fn), os.path.join(SERVE, fn))

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SERVE)
httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
print(f"server :{PORT} {noedge_name}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--enable-unsafe-webgpu", "--enable-features=Vulkan",
                  "--ignore-gpu-blocklist", "--use-angle=default"],
        )
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("pageerror:", e))
        page.goto(f"http://127.0.0.1:{PORT}/v3-stunning.html?g={noedge_name}", wait_until="load", timeout=30000)
        try:
            page.wait_for_function("window.__ready===true || window.__error", timeout=60000)
        except Exception as e:
            print("ready:", e)
        print("__error =", page.evaluate("window.__error || null"))
        page.wait_for_timeout(3000)   # morph 聚合完成
        page.screenshot(path=os.path.join(HERE, f"diag-{NAME}-gibnoedge-overview.png"))
        # 手動退到全景檔看整體節點雲
        page.evaluate("window.__setTier && window.__setTier('far')")
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(HERE, f"diag-{NAME}-gibnoedge-far.png"))
        print("camDist =", page.evaluate("window.__camDist()"))
        browser.close()
    httpd.shutdown()
    print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        httpd.shutdown()
