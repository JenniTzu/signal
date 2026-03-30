# ═══════════════════════════════════════════════════════════
# SIGNAL — analyst_agent.py
# Agent 1：策略分析師（時機判斷者）
# 只看技術面，不看基本面和估值
# ═══════════════════════════════════════════════════════════

import config

# Gemini 只在有 Key 時載入
def _get_gemini():
    if not config.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        return None


SYSTEM_PROMPT = """你是一位純技術面策略分析師。
你的角色：時機判斷者
你的核心問題：「現在按下扳機的時機對嗎？」

你的框架：
- 你只看技術訊號：RSI、成交量、200日均線偏離、產業ETF資金流向
- 你完全不管公司好不好、估值貴不貴
- RSI夠低、量能放大、技術面反轉，你就說時機到了
- 你完全不看基本面和估值

輸出格式（每檔股票）：
🟢 時機到 / 🟡 訊號出現中 / 🔴 尚未到位
＋ 一句話說明（必須提到RSI數值、量能倍數）

語氣：直接、自信，不要廢話，不要說「我認為」
語言：繁體中文
字數限制：每檔最多50字"""


def build_prompt(stocks: dict, sector_etfs: dict) -> str:
    lines = ["以下是今日技術數據，請對每檔股票給出判斷：\n"]

    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue
        rsi      = s.get("rsi14", "N/A")
        vol      = s.get("vol_ratio", "N/A")
        ma200dev = s.get("pct_from_ma200", "N/A")
        chg      = s.get("change_pct", "N/A")
        lines.append(
            f"• {sym}：現價${s['price']}  RSI={rsi}  "
            f"成交量倍數={vol}x  200MA偏離={ma200dev}%  今日漲跌={chg}%"
        )

    lines.append("\n產業ETF今日走勢：")
    for sym, etf in sector_etfs.items():
        lines.append(f"• {sym}：{etf.get('change_1d', 'N/A')}%（5日={etf.get('change_5d', 'N/A')}%）")

    lines.append("\n請對每檔股票給出：🟢時機到 / 🟡訊號出現中 / 🔴尚未到位 + 一句話說明")
    return "\n".join(lines)


def build_fallback(stocks: dict) -> dict:
    """無 Gemini API 時，用規則引擎產生分析"""
    results = {}
    for sym in (list(config.HOLDINGS.keys())
                + config.DIP_TARGETS
                + config.SWING_TARGETS):
        s = stocks.get(sym, {})
        if not s.get("price"):
            continue

        rsi = s.get("rsi14")
        vol = s.get("vol_ratio")
        ma  = s.get("pct_from_ma200")

        green_signals = 0
        yellow_signals = 0

        if rsi is not None:
            if rsi < 30: green_signals += 1
            elif rsi < 40: yellow_signals += 1

        if vol is not None:
            if vol >= 1.5: green_signals += 1
            elif vol >= 1.1: yellow_signals += 1

        if ma is not None:
            if ma < -15: green_signals += 1
            elif ma < -5: yellow_signals += 1

        if green_signals >= 2:
            status = "🟢"
            label  = "時機到"
            reason = (f"RSI={rsi}（超賣）+ 量能{vol}x放大"
                      if rsi and vol else "多項技術指標指向買點")
        elif green_signals + yellow_signals >= 2:
            status = "🟡"
            label  = "訊號出現中"
            reason = (f"RSI={rsi}，量能{vol}x，持續觀察"
                      if rsi and vol else "部分技術訊號浮現")
        else:
            status = "🔴"
            label  = "尚未到位"
            reason = (f"RSI={rsi}，量能{vol}x，暫無反轉訊號"
                      if rsi and vol else "技術面尚未出現進場訊號")

        results[sym] = {
            "status": status,
            "label":  label,
            "reason": reason,
            "rsi":    rsi,
            "vol":    vol,
        }

    return results


def run_analyst_agent(stocks: dict, sector_etfs: dict) -> dict:
    """主函式：策略分析師"""
    print("\n【analyst_agent.py】策略分析師執行中...")

    model = _get_gemini()

    if model:
        try:
            prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(stocks, sector_etfs)
            response = model.generate_content(prompt)
            raw_text = response.text

            # 解析回應（簡單按行拆分）
            per_stock = {}
            for sym in (list(config.HOLDINGS.keys())
                        + config.DIP_TARGETS
                        + config.SWING_TARGETS):
                for line in raw_text.split("\n"):
                    if sym in line:
                        if "🟢" in line:
                            status = "🟢"; label = "時機到"
                        elif "🟡" in line:
                            status = "🟡"; label = "訊號出現中"
                        elif "🔴" in line:
                            status = "🔴"; label = "尚未到位"
                        else:
                            continue
                        reason = line.split("：", 1)[-1].strip() if "：" in line else line.strip()
                        per_stock[sym] = {
                            "status": status,
                            "label":  label,
                            "reason": reason[:100],
                        }
                        break

            print("  ✅ Gemini 分析完成")
            return {
                "per_stock":  per_stock,
                "raw_text":   raw_text,
                "source":     "gemini",
            }
        except Exception as e:
            print(f"  ⚠️  Gemini 錯誤：{e}，改用規則引擎")

    # Fallback
    per_stock = build_fallback(stocks)
    print("  ✅ 規則引擎分析完成（Gemini Key 未設定）")
    return {
        "per_stock": per_stock,
        "raw_text":  "",
        "source":    "rule_engine",
    }


if __name__ == "__main__":
    mock_stocks = {
        "NVDA": {"price": 900, "rsi14": 28, "vol_ratio": 2.1,
                 "pct_from_ma200": -18, "change_pct": -3.2},
        "GOOGL": {"price": 155, "rsi14": 42, "vol_ratio": 1.0,
                  "pct_from_ma200": -5, "change_pct": -0.5},
    }
    result = run_analyst_agent(mock_stocks, {})
    print("\n── 策略分析師結果 ──")
    for sym, v in result["per_stock"].items():
        print(f"  {v['status']} {sym}：{v['reason']}")
