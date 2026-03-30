# ═══════════════════════════════════════════════════════════
# SIGNAL — swing_scanner.py
# 區塊二：波段機會掃描（三燈系統）
# 巴菲特燈 + 馬克斯燈 + 技術燈 → 三燈全綠才進
# ═══════════════════════════════════════════════════════════

import config


def buffett_light(stock: dict) -> dict:
    """
    巴菲特燈：商業本質
    🟢 護城河穩固 + FCF為正 + 毛利率未惡化
    """
    symbol = stock.get("symbol", "")

    # FCF 是否為正
    fcf = stock.get("fcf")
    fcf_positive = fcf is not None and fcf > 0

    # 毛利率趨勢（最新季度比最早季度好）
    trend = stock.get("gross_margin_trend")
    margin_ok = stock.get("gross_margin_improving")
    if margin_ok is None and trend:
        # 備用：只要毛利率 > 30% 視為 OK
        latest_margin = stock.get("gross_margin")
        margin_ok = latest_margin is not None and latest_margin > 0.30

    # ROE 品質
    roe = stock.get("roe")
    roe_ok = roe is not None and roe > 0.15  # ROE > 15%

    # 計分
    score = sum([bool(fcf_positive), bool(margin_ok), bool(roe_ok)])

    if score >= 3:
        status = "green"
        label  = "🟢 護城河穩固"
        reason = f"FCF正 + 毛利率穩健 + ROE>{roe * 100:.0f}%" if roe else "FCF正 + 基本面良好"
    elif score == 2:
        status = "yellow"
        label  = "🟡 部分條件成立"
        reason = f"{'FCF正' if fcf_positive else 'FCF負'} / {'毛利率OK' if margin_ok else '毛利率需觀察'} / ROE={roe * 100:.0f}%" if roe else "部分基本面待觀察"
    else:
        status = "red"
        label  = "🔴 基本面偏弱"
        reason = f"FCF={'正' if fcf_positive else '負'} / 毛利率={'OK' if margin_ok else '惡化'} / ROE={'OK' if roe_ok else '偏低'}"

    return {
        "status":        status,
        "label":         label,
        "reason":        reason,
        "score":         score,
        "fcf_positive":  fcf_positive,
        "margin_ok":     bool(margin_ok),
        "roe_ok":        roe_ok,
    }


def marks_light(stock: dict, pe_history: dict) -> dict:
    """
    霍華馬克斯燈：估值 + 市場情緒
    🟢 本益比低於10年均值15%以上 + 市場情緒偏恐懼
    """
    symbol = stock.get("symbol", "")
    pe_now = stock.get("pe_trailing")
    pe_hist = pe_history.get(symbol, {})
    pe_mean = pe_hist.get("pe_mean")

    # 估值判斷
    if pe_now and pe_mean:
        discount = (pe_mean - pe_now) / pe_mean  # 正數 = 低估
        undervalued = discount >= config.SWING_PE_DISCOUNT  # >= 15%
        valuation_label = f"PE {pe_now} vs 10年均值 {pe_mean}（折扣 {discount * 100:.0f}%）"
    else:
        undervalued = False
        discount = None
        valuation_label = f"PE={pe_now}（歷史均值待計算）" if pe_now else "PE數據不可用"

    # 分析師目標價 upside
    upside = stock.get("upside_pct")
    analyst_ok = upside is not None and upside > 10  # 上漲空間 > 10%

    if undervalued and (analyst_ok or pe_mean is None):
        status = "green"
        label  = "🟢 歷史低估值區"
        reason = valuation_label
    elif discount is not None and discount > 0:
        status = "yellow"
        label  = "🟡 估值中性"
        reason = f"{valuation_label}（需更大安全邊際）"
    else:
        status = "red"
        label  = "🔴 估值偏高"
        reason = valuation_label

    return {
        "status":       status,
        "label":        label,
        "reason":       reason,
        "pe_now":       pe_now,
        "pe_mean":      pe_mean,
        "discount_pct": round(discount * 100, 1) if discount is not None else None,
        "undervalued":  undervalued,
    }


def tech_light(stock: dict) -> dict:
    """
    技術燈：RSI + 成交量反轉訊號
    🟢 RSI < 35 開始往上 + 成交量放大1.5倍
    """
    rsi = stock.get("rsi14")
    vol_ratio = stock.get("vol_ratio")

    rsi_ok = rsi is not None and rsi < config.SWING_RSI_THRESHOLD   # < 35
    vol_ok = vol_ratio is not None and vol_ratio >= config.SWING_VOLUME_MULTIPLIER  # >= 1.5x

    if rsi_ok and vol_ok:
        status = "green"
        label  = "🟢 反轉訊號出現"
        reason = f"RSI={rsi}（< {config.SWING_RSI_THRESHOLD}超賣）+ 量能放大{vol_ratio}x"
    elif rsi_ok:
        status = "yellow"
        label  = "🟡 RSI超賣但量能不足"
        reason = f"RSI={rsi}，成交量={vol_ratio}x（需≥{config.SWING_VOLUME_MULTIPLIER}x）"
    elif vol_ok:
        status = "yellow"
        label  = "🟡 量能放大但RSI未到位"
        reason = f"成交量={vol_ratio}x，RSI={rsi}（需< {config.SWING_RSI_THRESHOLD}）"
    else:
        status = "red"
        label  = "🔴 尚未出現反轉訊號"
        reason = f"RSI={rsi}，成交量={vol_ratio}x"

    return {
        "status":   status,
        "label":    label,
        "reason":   reason,
        "rsi":      rsi,
        "vol_ratio": vol_ratio,
        "rsi_ok":   rsi_ok,
        "vol_ok":   vol_ok,
    }


def scan_swing_targets(stocks: dict, pe_history: dict, market_env: dict) -> list:
    """
    對波段潛力股跑三燈系統
    回傳：按三燈全綠優先排序
    """
    # 波段掃描目標 = 逢低加碼目標 + 波段潛力股
    targets = list(dict.fromkeys(config.DIP_TARGETS + config.SWING_TARGETS))

    results = []
    for sym in targets:
        stock = stocks.get(sym, {"symbol": sym})
        stock["symbol"] = sym

        b_light = buffett_light(stock)
        m_light = marks_light(stock, pe_history)
        t_light = tech_light(stock)

        green_count = sum(1 for l in [b_light, m_light, t_light] if l["status"] == "green")
        all_green   = green_count == 3

        results.append({
            "symbol":      sym,
            "price":       stock.get("price"),
            "change_pct":  stock.get("change_pct"),
            "buffett":     b_light,
            "marks":       m_light,
            "tech":        t_light,
            "green_count": green_count,
            "all_green":   all_green,
            "signal":      "🏆 今日最強訊號" if all_green else "",
        })

    # 全綠 → 二綠 → 一綠 → 零綠
    results.sort(key=lambda x: -x["green_count"])
    return results


def scan_nvda_special(stocks: dict, pe_history: dict) -> dict:
    """NVDA 特殊處理：並排顯示持股邏輯 + 波段三燈"""
    stock = stocks.get("NVDA", {"symbol": "NVDA"})
    stock["symbol"] = "NVDA"
    price = stock.get("price")
    cost  = config.HOLDINGS.get("NVDA", {}).get("cost")

    holding_info = {
        "cost":        cost,
        "price":       price,
        "pct_from_cost": round((price / cost - 1) * 100, 2) if price and cost else None,
        "label": (
            f"距成本 {(price / cost - 1) * 100:+.1f}%"
            if price and cost else "N/A"
        ),
    }

    b_light = buffett_light(stock)
    m_light = marks_light(stock, pe_history)
    t_light = tech_light(stock)
    green_count = sum(1 for l in [b_light, m_light, t_light] if l["status"] == "green")

    return {
        "holding":     holding_info,
        "buffett":     b_light,
        "marks":       m_light,
        "tech":        t_light,
        "green_count": green_count,
        "all_green":   green_count == 3,
    }


def run_swing_scanner(stocks: dict, pe_history: dict, market_env: dict) -> dict:
    """主函式"""
    print("\n【swing_scanner.py】執行波段機會掃描...")

    swing_results = scan_swing_targets(stocks, pe_history, market_env)
    nvda_special  = scan_nvda_special(stocks, pe_history)

    all_green_list = [r["symbol"] for r in swing_results if r["all_green"]]
    print(f"  三燈全綠：{all_green_list if all_green_list else '目前無'}")
    print("【swing_scanner.py】完成 ✅")

    return {
        "swing_results": swing_results,
        "nvda_special":  nvda_special,
        "all_green_list": all_green_list,
    }


# ── 測試用 ──────────────────────────────────────────────────

if __name__ == "__main__":
    mock_stocks = {
        "GOOGL": {"price": 150.0, "rsi14": 30, "vol_ratio": 1.8,
                  "fcf": 50e9, "gross_margin": 0.55, "roe": 0.25,
                  "pe_trailing": 18, "upside_pct": 15,
                  "gross_margin_improving": True, "change_pct": -2.0},
        "MSFT":  {"price": 380.0, "rsi14": 52, "vol_ratio": 1.0,
                  "fcf": 70e9, "gross_margin": 0.68, "roe": 0.40,
                  "pe_trailing": 30, "upside_pct": 8,
                  "gross_margin_improving": True, "change_pct": -0.3},
        "NVDA":  {"price": 900.0, "rsi14": 55, "vol_ratio": 1.2,
                  "fcf": 30e9, "gross_margin": 0.72, "roe": 0.90,
                  "pe_trailing": 45, "upside_pct": 20,
                  "gross_margin_improving": True, "change_pct": 1.5},
    }
    mock_pe = {
        "GOOGL": {"pe_mean": 22, "pe_median": 20, "pe_25pct": 16, "pe_75pct": 28},
        "MSFT":  {"pe_mean": 28, "pe_median": 26, "pe_25pct": 20, "pe_75pct": 35},
        "NVDA":  {"pe_mean": 60, "pe_median": 55, "pe_25pct": 30, "pe_75pct": 80},
    }
    mock_env = {"label": "Risk-Off", "emoji": "🔴"}

    result = run_swing_scanner(mock_stocks, mock_pe, mock_env)

    print("\n── 波段掃描結果 ──")
    for r in result["swing_results"]:
        signal_lbl = "三燈全綠！" if r['all_green'] else f"{r['green_count']}/3 燈"
        print(f"\n  {r['symbol']} ${r['price']}  {signal_lbl}")
        print(f"    巴菲特：{r['buffett']['label']}")
        print(f"    馬克斯：{r['marks']['label']}")
        print(f"    技術：  {r['tech']['label']}")

    print("\n── NVDA 特殊 ──")
    nv = result["nvda_special"]
    print(f"  持股狀態：{nv['holding']['label']}")
    print(f"  波段燈：{nv['green_count']}/3 綠")
