# ═══════════════════════════════════════════════════════════
# SIGNAL — dynamic_scanner.py
# 區塊三：S&P100 動態機會掃描
# 五個條件全部符合才顯示
# ═══════════════════════════════════════════════════════════

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

import config
from calculate import compute_rsi  # noqa: shared utility


def safe_float(val, default=None):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


def scan_single_stock(symbol: str) -> dict | None:
    """
    掃描單一股票，回傳符合條件的結果，不符合回傳 None
    條件：
    ① 市值 > 500億美元
    ② PE < 5年均值 × 0.8（折扣20%以上）
    ③ RSI < 35 開始反轉
    ④ 近5日成交量 > 60日均量 1.5倍
    ⑤ FCF > 0
    """
    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}

        # ① 市值
        market_cap = safe_float(info.get("marketCap"))
        if not market_cap or market_cap < config.DYNAMIC_MIN_MARKET_CAP:
            return None

        # ⑤ FCF
        fcf = safe_float(info.get("freeCashflow"))
        if fcf is None or fcf <= 0:
            return None

        # ② PE vs 5年均值
        pe_now = safe_float(info.get("trailingPE"))
        if pe_now is None or pe_now <= 0:
            return None

        # 取5年月度價格估算歷史PE（簡化版）
        hist = tk.history(period="5y", interval="1mo", auto_adjust=True)
        if hist is None or len(hist) < 24:
            return None

        trailing_eps = safe_float(info.get("trailingEps"))
        if not trailing_eps or trailing_eps <= 0:
            return None

        pe_list = []
        for _, row in hist.iterrows():
            p = float(row["Close"])
            pe = p / trailing_eps
            if 1 < pe < 500:
                pe_list.append(pe)

        if len(pe_list) < 12:
            return None

        pe_mean_5y = sum(pe_list) / len(pe_list)
        pe_threshold = pe_mean_5y * (1 - config.DYNAMIC_PE_DISCOUNT)  # 5年均值80%

        if pe_now > pe_threshold:
            return None  # PE 不夠便宜

        # ③④ RSI + 成交量（取1年日線）
        hist_1y = tk.history(period="1y", interval="1d", auto_adjust=True)
        if hist_1y is None or len(hist_1y) < 60:
            return None

        closes  = hist_1y["Close"].dropna()
        volumes = hist_1y["Volume"].dropna()

        rsi = compute_rsi(closes)
        if rsi is None or rsi >= config.DYNAMIC_RSI_MAX:
            return None

        vol_5  = volumes.iloc[-5:].mean()  if len(volumes) >= 5  else None
        vol_60 = volumes.iloc[-60:].mean() if len(volumes) >= 60 else None
        if vol_5 is None or vol_60 is None or vol_60 == 0:
            return None

        vol_ratio = vol_5 / vol_60
        if vol_ratio < config.DYNAMIC_VOLUME_MULT:
            return None

        # 全部條件通過
        price = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        return {
            "symbol":      symbol,
            "price":       price,
            "market_cap_b": round(market_cap / 1e9, 1),
            "pe_now":      round(pe_now, 1),
            "pe_mean_5y":  round(pe_mean_5y, 1),
            "pe_discount": round((pe_mean_5y - pe_now) / pe_mean_5y * 100, 1),
            "rsi14":       rsi,
            "vol_ratio":   round(vol_ratio, 2),
            "fcf_b":       round(fcf / 1e9, 1),
            "change_pct":  round((closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2)
                           if len(closes) >= 2 else None,
        }

    except Exception as e:
        return None


def run_dynamic_scanner(exclude_symbols: list = None) -> dict:
    """
    掃描全部 S&P100，回傳符合條件的股票清單
    exclude_symbols：已在觀察清單的股票不重複顯示
    """
    print("\n【dynamic_scanner.py】開始 S&P100 動態掃描...")
    exclude = set(exclude_symbols or [])
    results = []
    total   = len(config.SP100)

    for i, sym in enumerate(config.SP100, 1):
        if sym in exclude:
            print(f"  [{i:3d}/{total}] {sym:8s} — 跳過（已在觀察清單）")
            continue

        print(f"  [{i:3d}/{total}] {sym:8s}...", end=" ")
        hit = scan_single_stock(sym)
        if hit:
            results.append(hit)
            print(f"✅ 命中！PE折扣{hit['pe_discount']}% RSI{hit['rsi14']} Vol{hit['vol_ratio']}x")
        else:
            print("—")

    if results:
        results.sort(key=lambda x: -x["pe_discount"])   # 折扣最大的排前面

    summary = (
        f"今日發現 {len(results)} 個訊號"
        if results
        else "今日無訊號，繼續等待是最好的策略"
    )

    print(f"\n  {summary}")
    print("【dynamic_scanner.py】完成 ✅")

    return {
        "results":  results,
        "summary":  summary,
        "scanned":  total - len(exclude),
        "hits":     len(results),
    }


# ── 測試用（只掃5檔，節省時間）─────────────────────────────

if __name__ == "__main__":
    # 快速測試：只掃前5檔
    test_list_backup = config.SP100
    config.SP100 = config.SP100[:5]

    result = run_dynamic_scanner()

    config.SP100 = test_list_backup  # 還原

    print(f"\n── 動態掃描結果 ──")
    if result["results"]:
        for r in result["results"]:
            print(f"  ⚡ {r['symbol']:8s} ${r['price']}  "
                  f"PE={r['pe_now']} vs 5年均值{r['pe_mean_5y']}（折扣{r['pe_discount']}%）  "
                  f"RSI={r['rsi14']}  Vol={r['vol_ratio']}x")
    else:
        print(f"  {result['summary']}")
