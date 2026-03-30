# ═══════════════════════════════════════════════════════════
# SIGNAL — fetch_data.py
# 抓取即時市場數據：yfinance + Fear & Greed + FRED
# ═══════════════════════════════════════════════════════════

import sys
import os
# Windows 終端機 UTF-8 修正
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import warnings
warnings.filterwarnings("ignore")

import config

# ── 工具函式 ────────────────────────────────────────────────

def safe_get(obj, *keys, default=None):
    """安全取值，避免 KeyError / AttributeError"""
    try:
        val = obj
        for k in keys:
            val = val[k] if isinstance(val, dict) else getattr(val, k)
        return val if val is not None else default
    except Exception:
        return default


def safe_float(val, default=None):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


from calculate import compute_rsi  # 統一使用 calculate 模組


# ── 個股數據 ────────────────────────────────────────────────

def fetch_stock(symbol: str) -> dict:
    """抓取單一股票完整數據"""
    print(f"  抓取 {symbol}...")
    result = {"symbol": symbol, "error": None}

    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}

        # 是否為 ETF（ETF 無 PE/ROE/FCF 等基本面數據）
        quote_type = info.get("quoteType", "")
        result["is_etf"] = quote_type == "ETF"

        # 現價（ETF 用 regularMarketPrice 或 navPrice）
        price = (safe_float(info.get("currentPrice"))
                 or safe_float(info.get("regularMarketPrice"))
                 or safe_float(info.get("navPrice"))
                 or safe_float(info.get("previousClose")))
        result["price"] = price

        # 52 週高低點
        result["week52_high"] = safe_float(info.get("fiftyTwoWeekHigh"))
        result["week52_low"]  = safe_float(info.get("fiftyTwoWeekLow"))

        # 52 週距高點 / 低點 %
        if price and result["week52_high"]:
            result["pct_from_52w_high"] = round(
                (price / result["week52_high"] - 1) * 100, 2)
        else:
            result["pct_from_52w_high"] = None

        if price and result["week52_low"]:
            result["pct_from_52w_low"] = round(
                (price / result["week52_low"] - 1) * 100, 2)
        else:
            result["pct_from_52w_low"] = None

        # 市值
        result["market_cap"] = safe_float(info.get("marketCap") or info.get("totalAssets"))

        # 本益比、毛利率、ROE、FCF — ETF 跳過
        if result["is_etf"]:
            result["pe_trailing"]    = None
            result["pe_forward"]     = None
            result["gross_margin"]   = None
            result["roe"]            = None
            result["debt_to_equity"] = None
            result["fcf"]            = None
            result["fcf_yield"]      = None
            result["analyst_target"] = None
            result["analyst_count"]  = None
            result["upside_pct"]     = None
        else:
            result["pe_trailing"] = safe_float(info.get("trailingPE"))
            result["pe_forward"]  = safe_float(info.get("forwardPE"))
            result["gross_margin"] = safe_float(info.get("grossMargins"))
            result["roe"]          = safe_float(info.get("returnOnEquity"))
            result["debt_to_equity"] = safe_float(info.get("debtToEquity"))

            fcf = safe_float(info.get("freeCashflow"))
            mkt = result["market_cap"]
            result["fcf"] = fcf
            if fcf and mkt and mkt > 0:
                result["fcf_yield"] = round(fcf / mkt * 100, 2)
            else:
                result["fcf_yield"] = None

            result["analyst_target"] = safe_float(info.get("targetMeanPrice"))
            result["analyst_count"]  = info.get("numberOfAnalystOpinions")
            if price and result["analyst_target"]:
                result["upside_pct"] = round(
                    (result["analyst_target"] / price - 1) * 100, 2)
            else:
                result["upside_pct"] = None

        # 歷史價格（取1年）
        hist = tk.history(period="1y", interval="1d", auto_adjust=True)
        if hist is not None and len(hist) >= 20:
            closes = hist["Close"].dropna()
            volumes = hist["Volume"].dropna()

            # RSI-14
            result["rsi14"] = compute_rsi(closes)

            # 200日均線
            ma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else closes.mean()
            result["ma200"] = safe_float(ma200)
            if price and result["ma200"]:
                result["pct_from_ma200"] = round((price / result["ma200"] - 1) * 100, 2)
            else:
                result["pct_from_ma200"] = None

            # 成交量（近5日均量 vs 60日均量）
            vol_5  = volumes.iloc[-5:].mean()  if len(volumes) >= 5  else None
            vol_60 = volumes.iloc[-60:].mean() if len(volumes) >= 60 else None
            result["vol_5d"]  = safe_float(vol_5)
            result["vol_60d"] = safe_float(vol_60)
            if vol_5 and vol_60 and vol_60 > 0:
                result["vol_ratio"] = round(vol_5 / vol_60, 2)
            else:
                result["vol_ratio"] = None

            # 今日漲跌幅
            if len(closes) >= 2:
                result["change_pct"] = round(
                    (closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2)
            else:
                result["change_pct"] = None

        else:
            for k in ["rsi14", "ma200", "pct_from_ma200",
                      "vol_5d", "vol_60d", "vol_ratio", "change_pct"]:
                result[k] = None

        # 毛利率近5年趨勢（年報，ETF 跳過）
        if result["is_etf"]:
            result["gross_margin_trend"] = None
            result["gross_margin_improving"] = None
        else:
            try:
                fin = tk.financials  # 年報，欄位為日期
                if fin is not None and not fin.empty and "Gross Profit" in fin.index and "Total Revenue" in fin.index:
                    gp  = fin.loc["Gross Profit"].dropna()
                    rev = fin.loc["Total Revenue"].dropna()
                    margins = (gp / rev * 100).dropna()
                    if len(margins) >= 2:
                        result["gross_margin_trend"]    = [round(v, 2) for v in margins.values[:5]]
                        result["gross_margin_improving"] = bool(margins.iloc[0] > margins.iloc[-1])
                    else:
                        result["gross_margin_trend"] = None
                        result["gross_margin_improving"] = None
                else:
                    result["gross_margin_trend"] = None
                    result["gross_margin_improving"] = None
            except Exception:
                result["gross_margin_trend"] = None
                result["gross_margin_improving"] = None

        # 財報發布日期
        try:
            cal = tk.calendar
            if cal is not None:
                if isinstance(cal, dict) and "Earnings Date" in cal:
                    ed = cal["Earnings Date"]
                    result["earnings_date"] = str(ed[0].date()) if hasattr(ed[0], "date") else str(ed[0])
                elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.columns:
                    ed = cal["Earnings Date"].iloc[0]
                    result["earnings_date"] = str(ed.date()) if hasattr(ed, "date") else str(ed)
                else:
                    result["earnings_date"] = None
            else:
                result["earnings_date"] = None
        except Exception:
            result["earnings_date"] = None

        # 最新新聞（取前3則標題）
        try:
            news = tk.news or []
            result["news"] = [
                {
                    "title": n.get("content", {}).get("title", n.get("title", "")),
                    "url":   n.get("content", {}).get("canonicalUrl", {}).get("url",
                             n.get("link", ""))
                }
                for n in news[:3]
            ]
        except Exception:
            result["news"] = []

    except Exception as e:
        result["error"] = str(e)
        print(f"    ⚠️  {symbol} 發生錯誤：{e}")

    return result


# ── 產業 ETF 資金流向 ────────────────────────────────────────

def fetch_sector_etfs() -> dict:
    """抓取產業 ETF 漲跌幅與資金流向"""
    print("  抓取產業 ETF...")
    results = {}
    for sym in config.SECTOR_ETFS:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="5d", interval="1d", auto_adjust=True)
            if hist is not None and len(hist) >= 2:
                closes = hist["Close"].dropna()
                results[sym] = {
                    "price":      round(float(closes.iloc[-1]), 2),
                    "change_1d":  round((closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2),
                    "change_5d":  round((closes.iloc[-1] / closes.iloc[0]  - 1) * 100, 2),
                }
            else:
                results[sym] = {"price": None, "change_1d": None, "change_5d": None}
        except Exception as e:
            results[sym] = {"price": None, "change_1d": None, "change_5d": None, "error": str(e)}
    return results


# ── 市場指標（VIX、美債10年）──────────────────────────────────

def fetch_market_indicators() -> dict:
    """抓取 VIX 與美債殖利率"""
    print("  抓取市場指標（VIX / 美債）...")
    result = {}
    for sym in config.MARKET_INDICATORS:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="35d", interval="1d", auto_adjust=True)
            if hist is not None and len(hist) >= 2:
                closes = hist["Close"].dropna()
                label = "vix" if sym == "^VIX" else "tnx"
                result[label] = {
                    "value":   round(float(closes.iloc[-1]), 2),
                    "prev":    round(float(closes.iloc[-2]), 2),
                    "change":  round((closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2),
                    "history": [round(v, 2) for v in closes.iloc[-30:].values.tolist()],
                }
        except Exception as e:
            label = "vix" if sym == "^VIX" else "tnx"
            result[label] = {"value": None, "prev": None, "change": None, "history": [], "error": str(e)}
    return result


# ── Fear & Greed Index ───────────────────────────────────────

def fetch_fear_greed() -> dict:
    """抓取 CNN Fear & Greed 指數"""
    print("  抓取 Fear & Greed 指數...")
    try:
        import fear_greed
        score = fear_greed.get_score()
        rating = fear_greed.get_rating()

        # 歷史 30 天
        history_raw = fear_greed.get_history(last="30")
        history = [
            {"date": str(p.date)[:10], "score": round(float(p.score), 1)}
            for p in history_raw
        ] if history_raw else []

        return {
            "score":   round(float(score), 1),
            "rating":  rating,
            "history": history,
        }
    except Exception as e:
        print(f"    ⚠️  Fear & Greed 發生錯誤：{e}")
        return {"score": None, "rating": "待設定", "history": [], "error": str(e)}


# ── FRED — 信用利差（HY OAS）────────────────────────────────

def fetch_credit_spread() -> dict:
    """從 FRED 抓取垃圾債利差"""
    print("  抓取 Credit Spread（FRED）...")
    if not config.FRED_API_KEY:
        print("    ⓘ FRED_API_KEY 未設定，跳過")
        return {"value": None, "history": [], "status": "待設定"}

    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={config.FRED_HY_SPREAD_CODE}"
            f"&api_key={config.FRED_API_KEY}"
            f"&file_type=json"
            f"&sort_order=desc"
            f"&limit=35"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        obs  = data.get("observations", [])
        obs  = [o for o in obs if o.get("value") not in (".", None, "")]
        if not obs:
            return {"value": None, "history": [], "status": "無資料"}

        latest = float(obs[0]["value"]) * 100   # FRED 單位是 %，轉成 bps
        history = [
            {"date": o["date"], "value": round(float(o["value"]) * 100, 1)}
            for o in reversed(obs[:30])
        ]
        return {"value": round(latest, 1), "history": history, "status": "ok"}
    except Exception as e:
        print(f"    ⚠️  Credit Spread 發生錯誤：{e}")
        return {"value": None, "history": [], "status": "error", "error": str(e)}


# ── 主函式 ──────────────────────────────────────────────────

def fetch_all() -> dict:
    """抓取所有即時數據，回傳完整 dict"""
    print("\n【fetch_data.py】開始抓取市場數據...")

    # 個股（全部觀察清單）
    stocks = {}
    for sym in config.ALL_WATCHLIST:
        stocks[sym] = fetch_stock(sym)

    # 市場指標
    market = fetch_market_indicators()

    # 產業 ETF
    sector_etfs = fetch_sector_etfs()

    # Fear & Greed
    fgi = fetch_fear_greed()

    # Credit Spread
    credit_spread = fetch_credit_spread()

    print("【fetch_data.py】數據抓取完成 ✅\n")

    return {
        "stocks":        stocks,
        "market":        market,
        "sector_etfs":   sector_etfs,
        "fgi":           fgi,
        "credit_spread": credit_spread,
    }


# ── 測試用（直接執行此檔案）─────────────────────────────────

if __name__ == "__main__":
    import json
    data = fetch_all()

    # 顯示摘要
    print("─" * 50)
    print("市場指標：")
    vix = data["market"].get("vix", {})
    tnx = data["market"].get("tnx", {})
    print(f"  VIX    : {vix.get('value')}  （前日 {vix.get('prev')}）")
    print(f"  美債10年: {tnx.get('value')}%")

    fgi = data["fgi"]
    print(f"\nFear & Greed: {fgi.get('score')} — {fgi.get('rating')}")

    cs = data["credit_spread"]
    print(f"Credit Spread: {cs.get('value')} bps  [{cs.get('status')}]")

    print("\n個股摘要：")
    for sym, s in data["stocks"].items():
        if s.get("error"):
            print(f"  {sym:8s} ❌ {s['error'][:60]}")
        else:
            print(f"  {sym:8s} ${s.get('price', 'N/A'):>8}  "
                  f"RSI={s.get('rsi14', 'N/A'):>6}  "
                  f"Vol倍數={s.get('vol_ratio', 'N/A')}")

    print("\n產業 ETF：")
    for sym, e in data["sector_etfs"].items():
        print(f"  {sym:5s}  ${e.get('price', 'N/A'):>8}  "
              f"1日={e.get('change_1d', 'N/A')}%  5日={e.get('change_5d', 'N/A')}%")
