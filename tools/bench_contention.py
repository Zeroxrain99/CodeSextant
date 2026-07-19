"""量「跨專案隊頭阻塞」：一個專案在忙時，另一個專案的便宜查詢要等多久。

這支是 2026-07-18 併發根治的**可複現量測工具**，不是一次性腳本。交接檔說
「先觀察一週」，下一個接手的人要能跑出同一組數字來比對，所以它留在專案裡。

當時實測（同機同測試，只差程式碼）：
    舊碼（全域單一車道）：便宜查詢 1,486ms → 74,772ms（膨脹 50.3 倍）
    新碼（per-project 分片）：便宜查詢 624ms → 482ms（無膨脹）

用法：
    python tools/bench_contention.py --busy <大專案絕對路徑> --idle <小專案絕對路徑>
    python tools/bench_contention.py --busy ... --idle ... --json out.json

⚠ 這支會真的對 daemon 送一個重查詢（可能跑好幾分鐘），跑之前先確認沒有別的
代理正在等結果——它本身就會造成它要量的那種阻塞。
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
import urllib.request

# 前置探活用的短逾時（與被量測查詢的 --timeout 不同）：這只是問「daemon 在不在」，
# 健康檢查若慢到這個地步，本身就代表現在不該開始量測。
_HEALTH_PROBE_TIMEOUT_SEC = 10.0


def _timed_get(base: str, path: str, params: dict, timeout: float) -> tuple[float, str]:
    """回 (毫秒, 狀態)。逾時/連線失敗回例外類名而非拋出，讓量測跑完。"""
    url = f"{base}{path}?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read()
        status = str(resp.status if hasattr(resp, "status") else 200)
    except Exception as exc:  # noqa: BLE001 - 量測工具不該因單次失敗中斷
        status = type(exc).__name__
    return (time.perf_counter() - started) * 1000, status


def measure(base: str, busy_project: str, idle_project: str, *,
            busy_endpoint: str, idle_endpoint: str,
            timeout: float, settle_sec: float) -> dict:
    """先量基線，再讓 busy 專案佔住工作道，量 idle 專案的便宜查詢。"""
    solo_ms, solo_status = _timed_get(
        base, idle_endpoint, {"project": idle_project}, timeout)

    busy_result: dict = {}

    def _run_busy():
        ms, status = _timed_get(
            base, busy_endpoint, {"project": busy_project}, timeout)
        busy_result.update(ms=ms, status=status)

    busy_thread = threading.Thread(target=_run_busy)
    busy_thread.start()
    time.sleep(settle_sec)  # 讓重查詢先真的佔住車道再量

    loaded_ms, loaded_status = _timed_get(
        base, idle_endpoint, {"project": idle_project}, timeout)
    busy_thread.join(timeout=timeout)

    return {
        "idle_solo_ms": round(solo_ms, 1),
        "idle_solo_status": solo_status,
        "idle_under_load_ms": round(loaded_ms, 1),
        "idle_under_load_status": loaded_status,
        "busy_ms": round(busy_result.get("ms", -1), 1),
        "busy_status": busy_result.get("status"),
        "inflation_x": round(loaded_ms / solo_ms, 2) if solo_ms else None,
        "busy_project": busy_project,
        "idle_project": idle_project,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--busy", required=True, help="被灌重查詢的專案絕對路徑")
    p.add_argument("--idle", required=True, help="只發便宜查詢的另一個專案絕對路徑")
    p.add_argument("--base", default="http://127.0.0.1:8790", help="daemon 位址")
    p.add_argument("--busy-endpoint", default="/get_health")
    p.add_argument("--idle-endpoint", default="/comment_overview")
    # 600s 預設 = 涵蓋實測最慢的單次重查詢（find_duplicates 320s / 冷啟 map
    # 523.9s）再留餘裕；量小專案可調小，量 E:\ai-king 那種大庫請調大。
    p.add_argument("--timeout", type=float, default=600.0, help="單次請求上限秒數")
    p.add_argument("--settle", type=float, default=1.5,
                   help="發出重查詢後等幾秒才量便宜查詢")
    p.add_argument("--json", dest="json_out", help="把結果另存成 JSON")
    args = p.parse_args(argv)

    try:
        with urllib.request.urlopen(
                f"{args.base}/health", timeout=_HEALTH_PROBE_TIMEOUT_SEC) as r:
            health = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"連不上 daemon（{args.base}）：{exc}", file=sys.stderr)
        return 2

    result = measure(
        args.base, args.busy, args.idle,
        busy_endpoint=args.busy_endpoint, idle_endpoint=args.idle_endpoint,
        timeout=args.timeout, settle_sec=args.settle)
    result["daemon_pid"] = health.get("pid")
    result["heavy_work"] = health.get("heavy_work")

    print(f"daemon pid={result['daemon_pid']}")
    print(f"便宜查詢（單獨跑）      : {result['idle_solo_ms']:9.0f} ms  "
          f"{result['idle_solo_status']}")
    print(f"便宜查詢（別的專案忙碌）: {result['idle_under_load_ms']:9.0f} ms  "
          f"{result['idle_under_load_status']}")
    print(f"重查詢                  : {result['busy_ms']:9.0f} ms  "
          f"{result['busy_status']}")
    print(f"→ 膨脹 {result['inflation_x']} 倍"
          "（分片生效時應 ≈1；50 倍等級代表跨專案又擠在同一條車道）")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"已寫入 {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
