# ═══════════════════════════════════════════════════════════
# SIGNAL — buffett_agent.py
# Agent 2：巴菲特大腦（企業本質鑑定者）
# 只看基本面品質，不看技術面
# ═══════════════════════════════════════════════════════════

import config


def _get_gemini():
    if not config.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        return None


SYSTEM_PROMPT = """你是巴菲特的大腦，一位只關注商業本質的投資者。
你的角色：企業本質鑑定者
你的核心問題：「這家公司的商業本質值得長期擁有嗎？」

你的框架：
- 護城河類型：品牌 / 網路效應 / 成本優勢 / 轉換成本
- 毛利率趨勢（5年是否持續上升）
- ROE 是否連續多年 > 15%
- FCF 是否穩定為正且成長
- 近期新聞是否損害長期競爭力

你的原則：
- 你不計算精確買入價，只判斷商業本質是否優秀
- 好公司合理價格可以買，爛公司再便宜你也不碰
- 你完全不看RSI和技術面

輸出格式（每檔股票）：
✅ 護城河穩固，值得長期持有
⚠️ 出現需觀察的訊號
❌ 基本面出現惡化跡象
＋ 一句話說明原因

語氣：像老人說話，簡短、有智慧、不廢話
語言：繁體中文
字數限制：每檔最多60字"""


def build_prompt(stocks: dict) -> str:
    lines = ["以下是各公司基本面數據，請判斷每家公司的商業本質：\n"]

    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue

        fcf     = s.get("fcf")
        fcf_str = f"${fcf / 1e9:.1f}B" if fcf else "N/A"
        fcf_yield = s.get("fcf_yield")
        roe     = s.get("roe")
        roe_str = f"{roe * 100:.1f}%" if roe else "N/A"
        gm      = s.get("gross_margin")
        gm_str  = f"{gm * 100:.1f}%" if gm else "N/A"
        trend   = s.get("gross_margin_improving")
        trend_str = ("上升↑" if trend else "下降↓") if trend is not None else "N/A"
        de      = s.get("debt_to_equity")
        news    = "; ".join([n.get("title", "")[:40] for n in (s.get("news") or [])[:2]])

        lines.append(
            f"• {sym}：FCF={fcf_str} FCF殖利率={fcf_yield}%  "
            f"ROE={roe_str}  毛利率={gm_str}（趨勢{trend_str}）  "
            f"負債比={de}  近期新聞：{news[:80] if news else '無'}"
        )

    lines.append("\n請對每檔股票給出：✅護城河穩固 / ⚠️需觀察 / ❌基本面惡化 + 一句話說明")
    return "\n".join(lines)


def build_fallback(stocks: dict) -> dict:
    """無 Gemini 時用規則引擎判斷"""
    results = {}

    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue

        fcf  = s.get("fcf")
        roe  = s.get("roe")
        gm   = s.get("gross_margin")
        improving = s.get("gross_margin_improving")

        score = 0
        details = []

        if fcf and fcf > 0:
            score += 1
            details.append("FCF正")
        else:
            details.append("FCF需關注")

        if roe and roe > 0.15:
            score += 1
            details.append(f"ROE {roe * 100:.0f}%")
        elif roe:
            details.append(f"ROE {roe * 100:.0f}%偏低")

        if gm and gm > 0.30:
            score += 1
            details.append(f"毛利率{gm * 100:.0f}%")
        if improving:
            score += 1
            details.append("毛利率改善中")

        if score >= 4:
            status = "✅"; label = "護城河穩固，值得長期持有"
        elif score >= 2:
            status = "⚠️"; label = "基本面尚可，持續觀察"
        else:
            status = "❌"; label = "基本面偏弱，暫不考慮"

        reason = "、".join(details) if details else "數據不足"

        results[sym] = {
            "status": status,
            "label":  label,
            "reason": reason,
            "score":  score,
        }

    return results


def run_buffett_agent(stocks: dict) -> dict:
    """主函式：巴菲特大腦"""
    print("\n【buffett_agent.py】巴菲特大腦執行中...")

    model = _get_gemini()

    if model:
        try:
            prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(stocks)
            response = model.generate_content(prompt)
            raw_text = response.text

            per_stock = {}
            for sym in (list(config.HOLDINGS.keys())
                        + config.DIP_TARGETS
                        + config.SWING_TARGETS):
                for line in raw_text.split("\n"):
                    if sym in line:
                        if "✅" in line:
                            status = "✅"; label = "護城河穩固，值得長期持有"
                        elif "⚠️" in line or "⚠" in line:
                            status = "⚠️"; label = "出現需觀察的訊號"
                        elif "❌" in line:
                            status = "❌"; label = "基本面出現惡化跡象"
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
            return {"per_stock": per_stock, "raw_text": raw_text, "source": "gemini"}

        except Exception as e:
            print(f"  ⚠️  Gemini 錯誤：{e}，改用規則引擎")

    per_stock = build_fallback(stocks)
    print("  ✅ 規則引擎分析完成（Gemini Key 未設定）")
    return {"per_stock": per_stock, "raw_text": "", "source": "rule_engine"}


if __name__ == "__main__":
    mock_stocks = {
        "NVDA": {"price": 900, "fcf": 30e9, "fcf_yield": 1.5, "roe": 0.90,
                 "gross_margin": 0.72, "gross_margin_improving": True,
                 "debt_to_equity": 0.4,
                 "news": [{"title": "NVIDIA announces new AI chip"}]},
        "GOOGL": {"price": 155, "fcf": 50e9, "fcf_yield": 3.2, "roe": 0.25,
                  "gross_margin": 0.55, "gross_margin_improving": True,
                  "debt_to_equity": 0.1,
                  "news": [{"title": "Google AI search continues to grow"}]},
    }
    result = run_buffett_agent(mock_stocks)
    print("\n── 巴菲特大腦結果 ──")
    for sym, v in result["per_stock"].items():
        print(f"  {v['status']} {sym}：{v['reason']}")
