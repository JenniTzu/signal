# ═══════════════════════════════════════════════════════════
# SIGNAL — fetch_history.py
# 用 Alpha Vantage 抓取10年季度 EPS，計算歷史本益比區間
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

import requests
import json
import time
import statistics
import warnings
warnings.filterwarnings("ignore")

import config

# ETF 及無EPS的標的不計算PE（改回傳空結果）
ETF_SYMBOLS = {"QQQ", "SMH", "VTI", "GLD", "XLF", "XLE", "SPY", "IWM"}

CACHE_FILE = "pe_history_cache.json"   # 本地快取，避免重複呼叫 API


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def fetch_annual_eps_alphavantage(symbol: str) -> list[dict]:
    """用 Alpha Vantage 抓取年度 EPS（免費版）"""
    if not config.ALPHA_VANTAGE_KEY:
        return []

    url = (
        f"https://www.alphavantage.co/query"
        f"?function=EARNINGS"
        f"&symbol={symbol}"
        f"&apikey={config.ALPHA_VANTAGE_KEY}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        annual = data.get("annualEarnings", [])
        return annual  # [{"fiscalDateEnding": "YYYY-MM-DD", "reportedEPS": "X.XX"}, ...]
    except Exception as e:
        print(f"    ⚠️  Alpha Vantage EPS ({symbol}) 錯誤：{e}")
        return []


def fetch_price_history_yf(symbol: str) -> dict:
    """用 yfinance 抓取10年月收盤價（用來對應EPS計算本益比）"""
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)
        hist = tk.history(period="10y", interval="1mo", auto_adjust=True)
        if hist is None or hist.empty:
            return {}
        prices = {}
        for dt, row in hist.iterrows():
            key = str(dt.date())[:7]  # "YYYY-MM"
            prices[key] = round(float(row["Close"]), 2)
        return prices
    except Exception as e:
        print(f"    ⚠️  yfinance 價格歷史 ({symbol}) 錯誤：{e}")
        return {}


def compute_pe_history(symbol: str, use_cache: bool = True) -> dict:
    """
    計算一檔股票的10年歷史本益比區間
    回傳：{
        "symbol": str,
        "pe_mean": float,         # 10年平均本益比
        "pe_median": float,
        "pe_25pct": float,        # 25百分位（便宜）
        "pe_75pct": float,        # 75百分位（貴）
        "pe_min": float,
        "pe_max": float,
        "data_points": int,
        "source": "alpha_vantage" | "yfinance_fallback" | "unavailable"
    }
    """
    print(f"  計算 {symbol} 歷史本益比...")

    # ETF 不計算 PE
    if symbol in ETF_SYMBOLS:
        print(f"    -- ETF，跳過PE計算")
        return {"symbol": symbol, "pe_mean": None, "pe_median": None,
                "pe_25pct": None, "pe_75pct": None, "pe_min": None,
                "pe_max": None, "data_points": 0, "source": "etf"}

    cache = load_cache()
    if use_cache and symbol in cache:
        print(f"    使用快取")
        return cache[symbol]

    result = {
        "symbol": symbol,
        "pe_mean": None,
        "pe_median": None,
        "pe_25pct": None,
        "pe_75pct": None,
        "pe_min": None,
        "pe_max": None,
        "data_points": 0,
        "source": "unavailable"
    }

    # ── 方法1：Alpha Vantage（有 Key 才用）───────────────────
    if config.ALPHA_VANTAGE_KEY:
        eps_data = fetch_annual_eps_alphavantage(symbol)
        price_data = fetch_price_history_yf(symbol)
        time.sleep(12)  # 免費版每分鐘5次，保守等待

        pe_list = []
        for rec in eps_data:
            date_str = rec.get("fiscalDateEnding", "")[:7]  # "YYYY-MM"
            eps_str  = rec.get("reportedEPS", "")
            try:
                eps = float(eps_str)
                if eps <= 0:
                    continue
                # 取當月收盤價
                price = price_data.get(date_str)
                if price:
                    pe = round(price / eps, 1)
                    if 1 < pe < 500:  # 排除異常值
                        pe_list.append(pe)
            except Exception:
                continue

        if len(pe_list) >= 5:
            pe_list.sort()
            n = len(pe_list)
            result.update({
                "pe_mean":      round(statistics.mean(pe_list), 1),
                "pe_median":    round(statistics.median(pe_list), 1),
                "pe_25pct":     round(pe_list[int(n * 0.25)], 1),
                "pe_75pct":     round(pe_list[int(n * 0.75)], 1),
                "pe_min":       round(min(pe_list), 1),
                "pe_max":       round(max(pe_list), 1),
                "data_points":  n,
                "source":       "alpha_vantage"
            })
            cache[symbol] = result
            save_cache(cache)
            return result

    # ── 方法2：yfinance Fallback（用 trailing PE 估算）─────────
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)

        # 取10年月度本益比（用月收盤價 / TTM EPS）
        hist = tk.history(period="10y", interval="1mo", auto_adjust=True)
        info = tk.info or {}

        trailing_eps = float(info.get("trailingEps", 0) or 0)
        if trailing_eps <= 0:
            raise ValueError("EPS 不可用")

        # 用當前 trailing EPS 估算歷史本益比（近似）
        pe_list = []
        for _, row in hist.iterrows():
            price = float(row["Close"])
            pe = round(price / trailing_eps, 1)
            if 1 < pe < 500:
                pe_list.append(pe)

        if len(pe_list) >= 12:
            pe_list.sort()
            n = len(pe_list)
            result.update({
                "pe_mean":     round(statistics.mean(pe_list), 1),
                "pe_median":   round(statistics.median(pe_list), 1),
                "pe_25pct":    round(pe_list[int(n * 0.25)], 1),
                "pe_75pct":    round(pe_list[int(n * 0.75)], 1),
                "pe_min":      round(min(pe_list), 1),
                "pe_max":      round(max(pe_list), 1),
                "data_points": n,
                "source":      "yfinance_fallback"
            })
    except Exception as e:
        print(f"    ⚠️  yfinance fallback ({symbol}) 錯誤：{e}")

    cache[symbol] = result
    save_cache(cache)
    return result


def fetch_all_pe_history(force_refresh: bool = False) -> dict:
    """
    計算所有觀察標的的歷史本益比
    force_refresh=True 忽略快取重新計算
    """
    print("\n【fetch_history.py】計算歷史本益比區間...")

    all_symbols = (
        list(config.HOLDINGS.keys())
        + config.DIP_TARGETS
        + config.SWING_TARGETS
    )
    all_symbols = list(dict.fromkeys(all_symbols))

    pe_data = {}
    for sym in all_symbols:
        pe_data[sym] = compute_pe_history(sym, use_cache=not force_refresh)

    print("【fetch_history.py】歷史本益比計算完成 ✅\n")
    return pe_data


# ── 測試用 ──────────────────────────────────────────────────

if __name__ == "__main__":
    data = fetch_all_pe_history()
    print("\n歷史本益比摘要：")
    print(f"{'標的':8s} {'來源':20s} {'均值PE':>8} {'中位數':>8} "
          f"{'25%':>8} {'75%':>8} {'資料點':>6}")
    print("─" * 70)
    for sym, d in data.items():
        print(f"{sym:8s} {d['source']:20s} "
              f"{str(d['pe_mean']):>8} {str(d['pe_median']):>8} "
              f"{str(d['pe_25pct']):>8} {str(d['pe_75pct']):>8} "
              f"{d['data_points']:>6}")
