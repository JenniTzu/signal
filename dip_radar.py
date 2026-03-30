# ═══════════════════════════════════════════════════════════
# SIGNAL — dip_radar.py
# 區塊一：逢低加碼雷達
# 三選二觸發 → 掃描金字塔加碼點
# ═══════════════════════════════════════════════════════════

import config
from position_manager import check_pyramid_trigger


def check_dip_triggers(fgi_score, vix_value, credit_spread_bps) -> dict:
    """
    檢查三個觸發條件狀態
    回傳每個條件的狀態與距觸發差距
    """
    conditions = []

    # ① FGI < 25
    fgi_triggered = fgi_score is not None and fgi_score < config.FGI_THRESHOLD
    fgi_gap = round(fgi_score - config.FGI_THRESHOLD, 1) if fgi_score is not None else None
    conditions.append({
        "id":          "fgi",
        "label":       "恐慌指數 FGI",
        "description": f"CNN Fear & Greed < {config.FGI_THRESHOLD}（極度恐慌）",
        "threshold":   config.FGI_THRESHOLD,
        "value":       fgi_score,
        "triggered":   fgi_triggered,
        "gap":         fgi_gap,       # 正數 = 距觸發還差多少，負數 = 已超過
        "tip":         f"目前 {fgi_score}，距觸發 {fgi_gap:+.1f}" if fgi_score is not None else "數據不可用",
    })

    # ② VIX > 30
    vix_triggered = vix_value is not None and vix_value > config.VIX_THRESHOLD
    vix_gap = round(vix_value - config.VIX_THRESHOLD, 1) if vix_value is not None else None
    conditions.append({
        "id":          "vix",
        "label":       "波動率 VIX",
        "description": f"VIX > {config.VIX_THRESHOLD}（市場恐慌）",
        "threshold":   config.VIX_THRESHOLD,
        "value":       vix_value,
        "triggered":   vix_triggered,
        "gap":         vix_gap,
        "tip":         f"目前 {vix_value}，距觸發 {vix_gap:+.1f}" if vix_value is not None else "數據不可用",
    })

    # ③ Credit Spread > 500bps
    cs_triggered = credit_spread_bps is not None and credit_spread_bps > config.CREDIT_SPREAD_THRESHOLD
    cs_gap = round(credit_spread_bps - config.CREDIT_SPREAD_THRESHOLD, 1) if credit_spread_bps is not None else None
    conditions.append({
        "id":          "credit_spread",
        "label":       "信用利差 HY OAS",
        "description": f"垃圾債利差 > {config.CREDIT_SPREAD_THRESHOLD}bps（市場真正恐慌）",
        "threshold":   config.CREDIT_SPREAD_THRESHOLD,
        "value":       credit_spread_bps,
        "triggered":   cs_triggered,
        "gap":         cs_gap,
        "tip": (
            f"目前 {credit_spread_bps}bps，距觸發 {cs_gap:+.1f}bps"
            if credit_spread_bps is not None
            else "需設定 FRED_API_KEY"
        ),
    })

    triggered_count = sum(1 for c in conditions if c["triggered"])
    radar_active    = triggered_count >= 2   # 三選二

    return {
        "conditions":      conditions,
        "triggered_count": triggered_count,
        "radar_active":    radar_active,
        "summary": (
            f"⚡ 逢低加碼雷達啟動！{triggered_count}/3 條件成立"
            if radar_active
            else f"🔵 等待訊號 — {triggered_count}/3 條件成立（需 2 個）"
        ),
    }


def scan_dip_targets(stocks: dict, radar_active: bool) -> list:
    """
    掃描逢低加碼目標股的金字塔加碼觸發點
    只在 radar_active 時顯示詳細建議
    """
    results = []
    for sym in config.DIP_TARGETS:
        stock = stocks.get(sym, {})
        price = stock.get("price")

        item = {
            "symbol":     sym,
            "price":      price,
            "rsi14":      stock.get("rsi14"),
            "vol_ratio":  stock.get("vol_ratio"),
            "change_pct": stock.get("change_pct"),
            "pyramid":    None,
            "action":     "觀察",
        }

        if price:
            pyramid = check_pyramid_trigger(sym, price)
            item["pyramid"] = pyramid

            if radar_active and pyramid["triggered"]:
                levels = pyramid["levels"]
                deepest = levels[-1]["label"] if levels else ""
                item["action"] = f"建議加碼 — 已達{deepest}"
            elif not radar_active:
                item["action"] = "等待市場觸發"

        results.append(item)

    # 已觸發的置頂
    results.sort(key=lambda x: (
        0 if (x["pyramid"] and x["pyramid"]["triggered"] and radar_active) else 1
    ))

    return results


def run_dip_radar(market_data: dict, stocks: dict) -> dict:
    """主函式：執行逢低加碼雷達"""
    print("\n【dip_radar.py】執行逢低加碼雷達...")

    fgi_score        = market_data.get("fgi", {}).get("score")
    vix_value        = market_data.get("market", {}).get("vix", {}).get("value")
    credit_spread    = market_data.get("credit_spread", {}).get("value")

    triggers         = check_dip_triggers(fgi_score, vix_value, credit_spread)
    dip_targets      = scan_dip_targets(stocks, triggers["radar_active"])

    print(f"  {triggers['summary']}")
    print("【dip_radar.py】完成 ✅")

    return {
        "triggers":    triggers,
        "dip_targets": dip_targets,
    }


# ── 測試用 ──────────────────────────────────────────────────

if __name__ == "__main__":
    mock_market = {
        "fgi":           {"score": 22},
        "market":        {"vix": {"value": 32}},
        "credit_spread": {"value": 420},
    }
    mock_stocks = {
        "GOOGL": {"price": 160.0, "rsi14": 31, "vol_ratio": 1.8, "change_pct": -2.1},
        "MSFT":  {"price": 380.0, "rsi14": 45, "vol_ratio": 1.1, "change_pct": -0.5},
        "V":     {"price": 270.0, "rsi14": 38, "vol_ratio": 0.9, "change_pct": -1.2},
        "BRK-B": {"price": 430.0, "rsi14": 50, "vol_ratio": 1.0, "change_pct":  0.2},
        "VTI":   {"price": 240.0, "rsi14": 28, "vol_ratio": 2.1, "change_pct": -3.0},
        "ASML":  {"price": 620.0, "rsi14": 33, "vol_ratio": 1.6, "change_pct": -1.8},
        "AMD":   {"price":  95.0, "rsi14": 27, "vol_ratio": 2.3, "change_pct": -4.0},
    }

    result = run_dip_radar(mock_market, mock_stocks)

    print("\n── 觸發條件 ──")
    for cond in result["triggers"]["conditions"]:
        status = "✅" if cond["triggered"] else "⬜"
        print(f"  {status} {cond['label']}：{cond['tip']}")
    print(f"\n{result['triggers']['summary']}")

    print("\n── 逢低加碼目標股 ──")
    for item in result["dip_targets"]:
        p = item["pyramid"]
        triggered = p and p["triggered"]
        mark = "⚡" if triggered else "  "
        print(f"  {mark} {item['symbol']:6s}  ${item['price']}  "
              f"RSI={item['rsi14']}  Vol={item['vol_ratio']}x  "
              f"→ {item['action']}")
