# ═══════════════════════════════════════════════════════════
# SIGNAL — main.py
# 每日執行入口，串接所有模組
# ═══════════════════════════════════════════════════════════

import sys
import os
import json
from datetime import date, datetime

# Windows UTF-8 修正
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 模組載入 ────────────────────────────────────────────────
import config
from data    import fetch_data, fetch_history
from analysis import calculate, position_manager, dip_radar, swing_scanner, dynamic_scanner, backtest
from agents  import analyst_agent, buffett_agent, howard_marks_agent
from output  import update_data, deploy


def run(
    skip_dynamic_scan: bool = False,   # S&P100 掃描耗時，測試時可跳過
    skip_deploy:       bool = False,   # 測試模式不推送
    force_pe_refresh:  bool = False,   # 強制重新抓歷史 PE
    dry_run:           bool = False,   # 只執行到 update_data，不 deploy
):
    start_time = datetime.now()
    today      = str(date.today())

    print("=" * 60)
    print(f"  SIGNAL 每日分析  —  {today}")
    print(f"  In the noise, find the signal.")
    print("=" * 60)

    # ── Step 1：抓取即時數據 ─────────────────────────────────
    raw_data = fetch_data.fetch_all()

    # ── Step 2：歷史本益比（有快取則快，否則從 AV 抓）──────────
    pe_history = fetch_history.fetch_all_pe_history(force_refresh=force_pe_refresh)

    # ── Step 3：技術指標計算 ──────────────────────────────────
    signals = calculate.calc_all_signals(raw_data["stocks"])

    # ── Step 4：部位風險 ──────────────────────────────────────
    position_risk = position_manager.calc_position_risk(raw_data["stocks"])

    # ── Step 5：逢低加碼雷達 ──────────────────────────────────
    dip_result = dip_radar.run_dip_radar(raw_data, raw_data["stocks"])

    # ── Step 6：波段掃描 ──────────────────────────────────────
    market_env    = calculate.market_environment(
        raw_data.get("fgi", {}).get("score"),
        raw_data.get("market", {}).get("vix", {}).get("value"),
        raw_data.get("credit_spread", {}).get("value"),
    )
    swing_result  = swing_scanner.run_swing_scanner(
        raw_data["stocks"], pe_history, market_env
    )

    # ── Step 7：動態掃描（可跳過）────────────────────────────
    if skip_dynamic_scan:
        print("\n【dynamic_scanner.py】已跳過（skip_dynamic_scan=True）")
        dynamic_result = {
            "results": [], "summary": "動態掃描已跳過（測試模式）",
            "scanned": 0, "hits": 0
        }
    else:
        dynamic_result = dynamic_scanner.run_dynamic_scanner(
            exclude_symbols=config.ALL_WATCHLIST
        )

    # ── Step 8：三個 Agent ───────────────────────────────────
    analyst_result = analyst_agent.run_analyst_agent(
        raw_data["stocks"], raw_data.get("sector_etfs", {})
    )
    buffett_result = buffett_agent.run_buffett_agent(raw_data["stocks"])
    marks_result   = howard_marks_agent.run_howard_marks_agent(
        raw_data["stocks"], pe_history, raw_data
    )

    # ── Step 9：寫入 data.json ───────────────────────────────
    record = update_data.run_update(
        date_str        = today,
        raw_data        = raw_data,
        signals         = signals,
        position_risk   = position_risk,
        dip_result      = dip_result,
        swing_result    = swing_result,
        dynamic_result  = dynamic_result,
        analyst_result  = analyst_result,
        buffett_result  = buffett_result,
        marks_result    = marks_result,
        pe_history      = pe_history,
    )

    # ── Step 10：部署 GitHub Pages ───────────────────────────
    deploy_result = {"success": False, "skipped": True, "message": "已跳過"}
    if not skip_deploy and not dry_run:
        deploy_result = deploy.deploy_to_github(
            commit_message=f"signal: daily update {today}"
        )

    # ── 完成報告 ─────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    print("\n" + "=" * 60)
    print(f"  ✅ SIGNAL 分析完成  耗時 {elapsed} 秒")
    print(f"  日期：{today}")

    # 部位警示
    tc = position_risk.get("tech_concentration", {})
    if tc.get("is_warning"):
        print(f"  🔴 科技集中度警告：{tc.get('tech_pct_display')}")

    # 逢低加碼雷達
    triggers = dip_result.get("triggers", {})
    print(f"  逢低加碼雷達：{triggers.get('summary', '—')}")

    # 波段全綠
    all_green = swing_result.get("all_green_list", [])
    if all_green:
        print(f"  🏆 波段三燈全綠：{', '.join(all_green)}")

    # 動態掃描
    print(f"  動態掃描：{dynamic_result.get('summary', '—')}")

    # 部署狀態
    if deploy_result.get("success"):
        print(f"  🌐 網站已更新：{deploy_result.get('url')}")
    elif deploy_result.get("skipped"):
        print(f"  ⓘ 部署已跳過（測試模式）")

    print("=" * 60)

    return record


# ── CLI 執行 ─────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    # 回測模式：獨立執行，不跑每日分析
    if "--backtest" in args:
        backtest.run_backtest()
        sys.exit(0)

    skip_dynamic = "--skip-dynamic" in args
    skip_deploy  = "--skip-deploy"  in args or "--dry-run" in args
    force_pe     = "--force-pe"     in args
    dry_run      = "--dry-run"      in args

    run(
        skip_dynamic_scan = skip_dynamic,
        skip_deploy       = skip_deploy,
        force_pe_refresh  = force_pe,
        dry_run           = dry_run,
    )
