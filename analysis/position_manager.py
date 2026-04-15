# ═══════════════════════════════════════════════════════════
# SIGNAL — position_manager.py
# 部位風險計算、金字塔加碼邏輯、集中度警示
# ═══════════════════════════════════════════════════════════

import sys
import os
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from datetime import date, datetime
import config


# ── 工具 ────────────────────────────────────────────────────

def usd_to_twd(usd: float) -> float:
    return round(usd * config.USD_TWD_RATE, 0)


def next_fomc_days() -> dict:
    """計算距下一次 FOMC 會議天數"""
    today = date.today()
    future = [
        datetime.strptime(d, "%Y-%m-%d").date()
        for d in config.FOMC_DATES_2026
        if datetime.strptime(d, "%Y-%m-%d").date() >= today
    ]
    if not future:
        return {"date": "N/A", "days": None}
    next_date = min(future)
    days = (next_date - today).days
    return {"date": str(next_date), "days": days}


def next_earnings_days(stocks: dict) -> dict:
    """找最近一檔即將發布財報的股票"""
    today = date.today()
    upcoming = []
    for sym, s in stocks.items():
        ed = s.get("earnings_date")
        if not ed:
            continue
        try:
            ed_date = datetime.strptime(ed[:10], "%Y-%m-%d").date()
            if ed_date >= today:
                upcoming.append((ed_date, sym))
        except Exception:
            continue
    if not upcoming:
        return {"symbol": "N/A", "date": "N/A", "days": None}
    upcoming.sort()
    next_date, next_sym = upcoming[0]
    days = (next_date - today).days
    return {"symbol": next_sym, "date": str(next_date), "days": days}


# ── 集中度計算 ───────────────────────────────────────────────

def calc_portfolio_value(stocks: dict) -> dict:
    """
    用真實股數 × 當日現價計算各持股市值（USD → TWD）
    回傳各股市值明細與總市值
    """
    rate = config.USD_TWD_RATE
    breakdown = {}
    total_usd = 0.0

    for sym, holding in config.HOLDINGS.items():
        shares = holding.get("shares", 0) or 0
        cost   = holding.get("cost", 0)   or 0
        price  = stocks.get(sym, {}).get("price") or cost  # 抓不到現價就用成本
        value_usd = shares * price
        total_usd += value_usd
        breakdown[sym] = {
            "shares":    shares,
            "price":     round(price, 2),
            "value_usd": round(value_usd, 2),
            "value_twd": round(value_usd * rate, 0),
        }

    # 補上各股占比
    for sym in breakdown:
        v = breakdown[sym]["value_usd"]
        breakdown[sym]["pct"] = round(v / total_usd * 100, 1) if total_usd else 0

    return {
        "total_usd": round(total_usd, 2),
        "total_twd": round(total_usd * rate, 0),
        "breakdown": breakdown,
    }


def calc_tech_concentration(stocks: dict) -> dict:
    """
    計算科技集中度：QQQ + SMH + NVDA 佔總持股市值比例
    使用真實股數 × 當日現價計算
    """
    pv = calc_portfolio_value(stocks)
    total_usd  = pv["total_usd"]
    breakdown_all = pv["breakdown"]
    tech_symbols = ["QQQ", "SMH", "NVDA"]

    tech_usd = sum(
        breakdown_all.get(s, {}).get("value_usd", 0)
        for s in tech_symbols
    )
    tech_pct = tech_usd / total_usd if total_usd else 0

    breakdown = {
        s: {
            "cost_twd": round(breakdown_all.get(s, {}).get("value_twd", 0) / 10000, 1),
            "pct":      breakdown_all.get(s, {}).get("pct", 0),
        }
        for s in tech_symbols
    }

    return {
        "tech_pct":         round(tech_pct, 4),
        "tech_pct_display": f"{tech_pct * 100:.1f}%",
        "is_warning":       tech_pct > config.TECH_CONCENTRATION_WARN,
        "breakdown":        breakdown,
        "portfolio":        pv,   # 完整持股明細供前端使用
    }


# ── 若市場跌20%損失估計 ──────────────────────────────────────

def calc_drawdown_20pct(stocks: dict) -> dict:
    """
    估算若整體市場下跌 20%，持股損失
    使用真實持股市值計算（非固定比例）
    """
    pv          = calc_portfolio_value(stocks)
    total_cap   = config.TOTAL_CAPITAL_TWD
    invested_twd = pv["total_twd"]
    invested_pct = invested_twd / total_cap if total_cap else 0
    loss_twd     = invested_twd * 0.20

    return {
        "loss_twd":     round(loss_twd / 10000, 1),
        "loss_pct":     round(loss_twd / total_cap * 100, 1) if total_cap else 0,
        "invested_pct": round(invested_pct * 100, 1),
        "invested_twd": round(invested_twd / 10000, 1),
    }


# ── 可用子彈 ─────────────────────────────────────────────────

def calc_available_bullets() -> dict:
    """
    可用子彈 = 總資金 × 加碼上限 % （單次）
    """
    total      = config.TOTAL_CAPITAL_TWD
    per_trade  = round(total * config.ADD_POSITION_PCT / 10000, 1)  # 萬台幣

    # 金字塔各階子彈
    bullets = []
    for level in config.PYRAMID_LEVELS:
        bullets.append({
            "label":    level["label"],
            "drop_pct": level["drop_pct"] * 100,
            "amount_twd": round(per_trade * level["deploy_pct"], 1),  # 萬台幣
        })

    return {
        "per_trade_twd":   per_trade,
        "pyramid_bullets": bullets,
    }


# ── 金字塔加碼觸發判斷 ───────────────────────────────────────

def check_pyramid_trigger(symbol: str, current_price: float) -> dict:
    """
    判斷某標的是否觸發金字塔加碼
    - 持股：以成本價為基準
    - 逢低加碼目標股：以分析師目標價或近期高點為基準
    """
    holding  = config.HOLDINGS.get(symbol)
    base_price = None
    base_label = ""

    if holding and holding.get("cost"):
        base_price = holding["cost"]
        base_label = "成本價"

    if base_price is None or current_price is None:
        return {"triggered": False, "levels": [], "drop_pct": None,
                "base_price": None, "base_label": ""}

    drop_pct = (current_price / base_price - 1) * 100  # 負數表示跌幅

    triggered_levels = []
    for level in config.PYRAMID_LEVELS:
        threshold = level["drop_pct"] * 100   # 例如 -10, -20, -30
        if drop_pct <= threshold:
            triggered_levels.append({
                "label":     level["label"],
                "threshold": threshold,
                "current":   round(drop_pct, 1),
                "bullets_pct": level["deploy_pct"] * 100,
            })

    return {
        "triggered":   len(triggered_levels) > 0,
        "base_price":  base_price,
        "base_label":  base_label,
        "drop_pct":    round(drop_pct, 1),
        "levels":      triggered_levels,
    }


# ── 主函式 ──────────────────────────────────────────────────

def calc_position_risk(stocks: dict) -> dict:
    """整合所有部位風險指標"""
    print("\n【position_manager.py】計算部位風險...")

    tech_conc  = calc_tech_concentration(stocks)
    drawdown   = calc_drawdown_20pct(stocks)
    bullets    = calc_available_bullets()
    fomc       = next_fomc_days()
    earnings   = next_earnings_days(stocks)

    # 各持股金字塔狀態
    pyramid_status = {}
    for sym, holding in config.HOLDINGS.items():
        price = stocks.get(sym, {}).get("price")
        if price:
            pyramid_status[sym] = check_pyramid_trigger(sym, price)

    print("【position_manager.py】部位風險計算完成 ✅")

    return {
        "tech_concentration": tech_conc,
        "drawdown_20pct":     drawdown,
        "bullets":            bullets,
        "fomc":               fomc,
        "next_earnings":      earnings,
        "pyramid_status":     pyramid_status,
        "total_capital_twd":  config.TOTAL_CAPITAL_TWD,
    }


# ── 測試用 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 用模擬數據測試
    mock_stocks = {
        "NVDA": {"price": 900.0, "earnings_date": "2026-05-15"},
        "SMH":  {"price": 195.0, "earnings_date": None},
        "QQQ":  {"price": 480.0, "earnings_date": None},
    }

    result = calc_position_risk(mock_stocks)

    print("\n── 部位風險報告 ──")
    tc = result["tech_concentration"]
    print(f"科技集中度：{tc['tech_pct_display']}  {'🔴 警告' if tc['is_warning'] else '✅ 正常'}")
    for sym, b in tc["breakdown"].items():
        print(f"  {sym}: {b['pct']}%（{b['cost_twd']}萬台幣）")

    d = result["drawdown_20pct"]
    print(f"\n若市場跌20%損失：{d['loss_twd']}萬台幣（{d['loss_pct']}%）")

    b = result["bullets"]
    print(f"\n每次加碼上限：{b['per_trade_twd']}萬台幣")
    for level in b["pyramid_bullets"]:
        print(f"  {level['label']}：動用{level['amount_twd']}萬")

    fomc = result["fomc"]
    print(f"\n距下次 FOMC：{fomc['days']} 天（{fomc['date']}）")

    earn = result["next_earnings"]
    print(f"距下次財報：{earn['days']} 天（{earn['symbol']} / {earn['date']}）")

    print("\n金字塔加碼狀態：")
    for sym, ps in result["pyramid_status"].items():
        if ps["triggered"]:
            print(f"  {sym} ⚡ 觸發！距成本 {ps['drop_pct']}%")
            for lv in ps["levels"]:
                print(f"    → {lv['label']}：動用{lv['bullets_pct']}%子彈")
        else:
            print(f"  {sym} 距成本 {ps['drop_pct']}%  未觸發")
