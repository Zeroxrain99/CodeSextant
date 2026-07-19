"""一鍵開 CodeSextant 代碼星圖工作台（daemon serve 版、由 開啟星圖.vbs 隱藏啟動）。
ensure 常駐引擎 daemon（:8790）→ Edge/Chrome 開 http://127.0.0.1:8790/starmap
（輸入 repo 絕對路徑 → Enter 即時出圖、帶完整代碼）。
daemon 常駐（多代理共用、不關分頁就停）；⛔ 用 Edge/Chrome（WebGPU 必須，Firefox 紅屏）。"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.dirname(HERE)   # E:\ai-king\項目資料\CodeSextant
PY = sys.executable if os.path.basename(sys.executable).lower().startswith("py") else r"C:\Python311\python.exe"
URL = "http://127.0.0.1:8790/starmap"

# 1) ensure 常駐引擎 daemon（冪等：已跑同 PID 不重開）
subprocess.run([PY, "-m", "codesextant.daemon", "ensure"], cwd=CS, capture_output=True)

# 2) 等 daemon 起來（輪詢 /health）
for _ in range(40):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8790/health", timeout=2) as r:
            if r.status == 200:
                break
    except Exception:
        time.sleep(0.5)

# 3) 開瀏覽器（Edge/Chrome 優先，WebGPU 必須）
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
for exe in EDGE + CHROME:
    if os.path.exists(exe):
        subprocess.Popen([exe, URL])
        break
else:
    webbrowser.open(URL)
