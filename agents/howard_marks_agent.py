# ═══════════════════════════════════════════════════════════
# SIGNAL — howard_marks_agent.py
# Agent 3：霍華馬克斯大腦（風險與週期評估者）
# 市場鐘擺 + 歷史估值位置
# ═══════════════════════════════════════════════════════════

import config


def _get_gemini():
    if not config.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        return genai.GenerativeModel("gemini-2.0-flash")
    except Exception:
        return None


SYSTEM_PROMPT = """你是霍華馬克斯的大腦，一位專注於風險與市場週期的投資者。
你的角色：風險與週期評估者
你的核心問題：「在當前市場環境下，這個價格的風險合理嗎？」

你的框架：
市場層（鐘擺位置）：
- Credit Spread：< 300bps=市場過度樂觀，300-500bps=正常，> 500bps=機會浮現，> 800bps=歷史性危機
- FGI 趨勢方向（從極度恐慌開始回升才是買點，不是恐慌中）
- VIX 方向（上升方向更危險）

個股層：
- 現價本益比 vs 該股10年歷史均值（折扣15%以上才算低估）
- 分析師目標價 vs 現價（upside空間）

你的原則：
- 你不管公司好不好，只看現在的價格在歷史風險報酬分佈裡的位置
- 鐘擺偏恐懼端 + 個股歷史低估值 = 風險合理
- 你完全不看RSI和技術面

輸出：
1. 市場鐘擺：貪婪端 / 中性 / 恐懼端（一句話說明）
2. 每檔個股：🟢歷史低估值區 / 🟡估值中性 / 🔴仍在歷史高估值區 + 一句話

語氣：深沉、謙遜，強調「我不知道」的謙遜哲學
語言：繁體中文
字數：每檔最多60字"""


def assess_market_pendulum(fgi_score, vix_value, credit_spread_bps) -> dict:
    """判斷市場鐘擺位置"""
    fear_score = 0

    if fgi_score is not None:
        if fgi_score < 25:   fear_score += 2
        elif fgi_score < 40: fear_score += 1
        elif fgi_score > 65: fear_score -= 1
        elif fgi_score > 80: fear_score -= 2

    if vix_value is not None:
        if vix_value > 35:   fear_score += 2
        elif vix_value > 25: fear_score += 1
        elif vix_value < 15: fear_score -= 1

    if credit_spread_bps is not None:
        if credit_spread_bps > 800:   fear_score += 3
        elif credit_spread_bps > 500: fear_score += 2
        elif credit_spread_bps > 300: fear_score += 1
        elif credit_spread_bps < 250: fear_score -= 2

    if fear_score >= 3:
        return {"label": "恐懼端", "emoji": "🔴", "detail": "市場恐慌，鐘擺偏向極端恐懼"}
    elif fear_score >= 1:
        return {"label": "偏恐懼", "emoji": "🟡", "detail": "市場情緒偏保守，尚未到達極端"}
    elif fear_score == 0:
        return {"label": "中性",   "emoji": "🟡", "detail": "市場情緒中性，風險報酬均衡"}
    elif fear_score >= -2:
        return {"label": "偏貪婪", "emoji": "🟡", "detail": "市場偏樂觀，需提高安全邊際"}
    else:
        return {"label": "貪婪端", "emoji": "🔴", "detail": "市場過度樂觀，風險被低估"}


def assess_stock_valuation(symbol: str, stock: dict, pe_history: dict) -> dict:
    """判斷個股歷史估值位置"""
    pe_now = stock.get("pe_trailing")
    pe_hist = pe_history.get(symbol, {})
    pe_mean = pe_hist.get("pe_mean")
    pe_25   = pe_hist.get("pe_25pct")
    pe_75   = pe_hist.get("pe_75pct")
    upside  = stock.get("upside_pct")

    if pe_now and pe_mean:
        discount = (pe_mean - pe_now) / pe_mean * 100
        if discount >= 15 and (pe_25 is None or pe_now <= pe_75):
            status = "🟢"
            label  = "歷史低估值區，風險報酬合理"
            reason = f"PE={pe_now} vs 10年均值{pe_mean}（低估{discount:.0f}%）"
        elif discount >= 0:
            status = "🟡"
            label  = "估值中性，需更大安全邊際"
            reason = f"PE={pe_now} vs 10年均值{pe_mean}（折扣{discount:.0f}%，不夠大）"
        else:
            status = "🔴"
            label  = "仍在歷史高估值區，風險偏高"
            reason = f"PE={pe_now} vs 10年均值{pe_mean}（溢價{-discount:.0f}%）"
    elif pe_now:
        # 無歷史均值，用分析師目標價判斷
        if upside and upside > 15:
            status = "🟡"; label = "估值中性"; reason = f"PE={pe_now}，分析師目標上漲空間{upside}%"
        elif upside and upside < -5:
            status = "🔴"; label = "估值偏高"; reason = f"PE={pe_now}，已超過分析師目標價"
        else:
            status = "🟡"; label = "估值中性"; reason = f"PE={pe_now}，歷史均值待計算"
    else:
        status = "🟡"; label = "數據不足"; reason = "PE數據不可用，無法評估"

    return {
        "status": status,
        "label":  label,
        "reason": reason,
        "pe_now": pe_now,
        "pe_mean": pe_mean,
    }


def build_prompt(stocks: dict, pe_history: dict, market_data: dict) -> str:
    fgi     = market_data.get("fgi", {})
    vix     = market_data.get("market", {}).get("vix", {})
    cs      = market_data.get("credit_spread", {})

    lines = [
        "市場環境數據：",
        f"• FGI={fgi.get('score')} ({fgi.get('rating')})",
        f"• VIX={vix.get('value')} 方向：{'上升↑' if (vix.get('change') or 0) > 0 else '下降↓'}",
        f"• 信用利差={cs.get('value')} bps",
        "",
        "個股估值數據：",
    ]

    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue
        ph    = pe_history.get(sym, {})
        pe_m  = ph.get("pe_mean", "N/A")
        pe_25 = ph.get("pe_25pct", "N/A")
        pe_75 = ph.get("pe_75pct", "N/A")
        lines.append(
            f"• {sym}：現價${s['price']}  PE={s.get('pe_trailing', 'N/A')}  "
            f"10年均值PE={pe_m}（25%={pe_25} / 75%={pe_75}）  "
            f"分析師目標upside={s.get('upside_pct', 'N/A')}%"
        )

    lines.append(
        "\n請給出：1.市場鐘擺位置  2.每檔股票估值評估 🟢低估值區/🟡中性/🔴高估值區 + 一句說明"
    )
    return "\n".join(lines)


def build_fallback(stocks: dict, pe_history: dict, market_data: dict) -> dict:
    """無 Gemini 時的規則引擎"""
    fgi_score     = market_data.get("fgi", {}).get("score")
    vix_value     = market_data.get("market", {}).get("vix", {}).get("value")
    credit_spread = market_data.get("credit_spread", {}).get("value")

    pendulum = assess_market_pendulum(fgi_score, vix_value, credit_spread)

    per_stock = {}
    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue
        per_stock[sym] = assess_stock_valuation(sym, s, pe_history)

    return {"pendulum": pendulum, "per_stock": per_stock}


def run_howard_marks_agent(stocks: dict, pe_history: dict, market_data: dict) -> dict:
    """主函式：霍華馬克斯大腦"""
    print("\n【howard_marks_agent.py】霍華馬克斯大腦執行中...")

    model = _get_gemini()
    fgi_score     = market_data.get("fgi", {}).get("score")
    vix_value     = market_data.get("market", {}).get("vix", {}).get("value")
    credit_spread = market_data.get("credit_spread", {}).get("value")
    pendulum      = assess_market_pendulum(fgi_score, vix_value, credit_spread)

    if model:
        try:
            prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(stocks, pe_history, market_data)
            response = model.generate_content(prompt)
            raw_text = response.text

            per_stock = {}
            for sym in (list(config.HOLDINGS.keys())
                        + config.DIP_TARGETS
                        + config.SWING_TARGETS):
                for line in raw_text.split("\n"):
                    if sym in line:
                        if "🟢" in line:
                            status = "🟢"; label = "歷史低估值區，風險報酬合理"
                        elif "🟡" in line:
                            status = "🟡"; label = "估值中性，需更大安全邊際"
                        elif "🔴" in line:
                            status = "🔴"; label = "仍在歷史高估值區，風險偏高"
                        else:
                            continue
                        reason = line.split("：", 1)[-1].strip() if "：" in line else line.strip()
                        per_stock[sym] = {
                            "status": status,
                            "label":  label,
                            "reason": reason[:120],
                        }
                        break

            print("  ✅ Gemini 分析完成")
            return {
                "pendulum":  pendulum,
                "per_stock": per_stock,
                "raw_text":  raw_text,
                "source":    "gemini",
            }
        except Exception as e:
            print(f"  ⚠️  Gemini 錯誤：{e}，改用規則引擎")

    fallback = build_fallback(stocks, pe_history, market_data)
    print("  ✅ 規則引擎分析完成（Gemini Key 未設定）")
    return {
        "pendulum":  fallback["pendulum"],
        "per_stock": fallback["per_stock"],
        "raw_text":  "",
        "source":    "rule_engine",
    }


if __name__ == "__main__":
    mock_stocks = {
        "NVDA":  {"price": 900, "pe_trailing": 45, "upside_pct": 18},
        "GOOGL": {"price": 155, "pe_trailing": 18, "upside_pct": 20},
    }
    mock_pe = {
        "NVDA":  {"pe_mean": 60, "pe_25pct": 30, "pe_75pct": 80},
        "GOOGL": {"pe_mean": 22, "pe_25pct": 16, "pe_75pct": 28},
    }
    mock_market = {
        "fgi":           {"score": 22, "rating": "Extreme Fear"},
        "market":        {"vix": {"value": 32, "change": 5}},
        "credit_spread": {"value": 420},
    }
    result = run_howard_marks_agent(mock_stocks, mock_pe, mock_market)
    pend = result["pendulum"]
    print(f"\n市場鐘擺：{pend['emoji']} {pend['label']} — {pend['detail']}")
    print("\n── 霍華馬克斯個股評估 ──")
    for sym, v in result["per_stock"].items():
        print(f"  {v['status']} {sym}：{v['reason']}")
