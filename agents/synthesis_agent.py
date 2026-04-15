# ═══════════════════════════════════════════════════════════
# SIGNAL — synthesis_agent.py
# 綜合裁判：把三個 Agent 的結論送給 Gemini，取得最終判斷
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


SYSTEM_PROMPT = """你是一位投資決策裁判，負責整合三位分析師的觀點，給出最終建議。

三位分析師的角色：
- 策略分析師：只看技術面（RSI、成交量、均線）
- 巴菲特大腦：只看基本面（護城河、FCF、ROE、毛利率）
- 霍華馬克斯大腦：只看估值與週期（本益比歷史位置、市場鐘擺）

你的任務：
1. 整合三個視角，給每檔股票一句「現在該怎麼做」的建議
2. 若三者一致 → 信心更高，語氣直接
3. 若三者分歧 → 說明分歧核心，建議等待哪個條件改變

輸出格式（每檔股票）：
【股票代號】結論：一句話（最多50字）

語言：繁體中文
不要廢話，直接給結論"""


def build_prompt(analyst_result: dict, buffett_result: dict,
                 marks_result: dict, stocks: dict) -> str:
    lines = ["以下是三位分析師對各標的的獨立判斷，請整合給出最終建議：\n"]

    all_symbols = list(dict.fromkeys(
        list(config.HOLDINGS.keys()) + config.DIP_TARGETS + config.SWING_TARGETS
    ))

    pendulum = marks_result.get("pendulum", {})
    if pendulum:
        lines.append(f"市場鐘擺：{pendulum.get('emoji', '')} {pendulum.get('label', '')} — {pendulum.get('detail', '')}\n")

    for sym in all_symbols:
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue

        a = analyst_result.get("per_stock", {}).get(sym, {})
        b = buffett_result.get("per_stock", {}).get(sym, {})
        m = marks_result.get("per_stock", {}).get(sym, {})

        if not any([a, b, m]):
            continue

        lines.append(f"── {sym}（現價 ${s.get('price')}）")
        if a:
            lines.append(f"  策略師：{a.get('status', '')} {a.get('reason', '')}")
        if b:
            lines.append(f"  巴菲特：{b.get('status', '')} {b.get('reason', '')}")
        if m:
            lines.append(f"  馬克斯：{m.get('status', '')} {m.get('reason', '')}")
        lines.append("")

    lines.append("請對每檔股票給出【代號】結論：一句話建議")
    return "\n".join(lines)


def build_fallback(analyst_result: dict, buffett_result: dict,
                   marks_result: dict) -> dict:
    """無 Gemini 時，用共識/分歧邏輯產生文字結論"""

    def to_score(status):
        if status in ("🟢", "✅"): return 1
        if status in ("🔴", "❌"): return -1
        return 0

    all_symbols = list(dict.fromkeys(
        list(config.HOLDINGS.keys()) + config.DIP_TARGETS + config.SWING_TARGETS
    ))

    per_stock = {}
    for sym in all_symbols:
        a = analyst_result.get("per_stock", {}).get(sym, {})
        b = buffett_result.get("per_stock", {}).get(sym, {})
        m = marks_result.get("per_stock", {}).get(sym, {})

        scores = [
            to_score(a.get("status", "")) if a else None,
            to_score(b.get("status", "")) if b else None,
            to_score(m.get("status", "")) if m else None,
        ]
        valid = [s for s in scores if s is not None]
        if not valid:
            continue

        total = sum(valid)
        all_same = len(set(valid)) == 1

        if total >= 2:
            conclusion = "三個視角均支持，可考慮布局" if all_same else "多數視角正面，可小量布局觀察"
        elif total <= -2:
            conclusion = "三個視角均保守，建議繼續觀望" if all_same else "多數視角保守，等待訊號改善"
        else:
            conclusion = "三個視角出現分歧，建議等待共識出現再行動"

        per_stock[sym] = {"conclusion": conclusion, "score": total}

    return per_stock


def run_synthesis_agent(analyst_result: dict, buffett_result: dict,
                        marks_result: dict, stocks: dict) -> dict:
    """主函式：綜合裁判"""
    print("\n【synthesis_agent.py】綜合裁判執行中...")

    model = _get_gemini()

    if model:
        try:
            prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(
                analyst_result, buffett_result, marks_result, stocks
            )
            response = model.generate_content(prompt)
            raw_text = response.text

            # 解析每股結論
            per_stock = {}
            all_symbols = list(dict.fromkeys(
                list(config.HOLDINGS.keys()) + config.DIP_TARGETS + config.SWING_TARGETS
            ))
            for sym in all_symbols:
                for line in raw_text.split("\n"):
                    if sym in line and "結論" in line:
                        conclusion = line.split("結論：", 1)[-1].strip() if "結論：" in line else line.strip()
                        per_stock[sym] = {"conclusion": conclusion[:100]}
                        break

            print("  ✅ Gemini 綜合裁判完成")
            return {
                "per_stock": per_stock,
                "raw_text":  raw_text,
                "source":    "gemini",
            }

        except Exception as e:
            print(f"  ⚠️  Gemini 錯誤：{e}，改用規則引擎")

    per_stock = build_fallback(analyst_result, buffett_result, marks_result)
    print("  ✅ 規則引擎綜合完成（Gemini Key 未設定）")
    return {
        "per_stock": per_stock,
        "raw_text":  "",
        "source":    "rule_engine",
    }
