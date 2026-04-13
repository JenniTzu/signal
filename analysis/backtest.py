# ═══════════════════════════════════════════════════════════
# SIGNAL — backtest.py
# 歷史回測：驗證兩個核心訊號的真實勝率
#
# 訊號A（價值型逢低）：距52週高點跌>20% + PE低於10年均值15%
# 訊號B（技術反轉）  ：距200日均線跌>15% + 成交量放大1.5倍
#
# 對每個訊號計算：30/60/90天勝率、平均盈虧、期望值
# ═══════════════════════════════════════════════════════════

import os
import json
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import yfinance as yf
from datetime import date

import config

# ── 參數 ────────────────────────────────────────────────────

SIGNAL_A_52W_DROP    = -20.0   # 距52週高點跌幅門檻（%）
SIGNAL_A_PE_DISCOUNT =  15.0   # PE低於10年均值門檻（%）
SIGNAL_B_MA200_DROP  = -15.0   # 距200日均線跌幅門檻（%）
SIGNAL_B_VOL_MULT    =   1.5   # 成交量放大倍數門檻

HOLDING_PERIODS = [30, 60, 90]  # 持有天數（交易日）

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(_ROOT, "cache", "backtest_results.json")
PE_CACHE   = os.path.join(_ROOT, "cache", "pe_history_cache.json")

# ETF 沒有PE/FCF，排除訊號A的PE判斷，訊號B可用
ETF_SYMBOLS = {"QQQ", "SMH", "VTI", "GLD"}


# ── 工具函式 ────────────────────────────────────────────────

def load_pe_cache() -> dict:
    if os.path.exists(PE_CACHE):
        with open(PE_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def safe_float(val, default=None):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


# ── 數據抓取 ────────────────────────────────────────────────

def fetch_history(symbol: str):
    """抓取5年日線數據，回傳 DataFrame 或 None"""
    try:
        tk   = yf.Ticker(symbol)
        hist = tk.history(period="5y", interval="1d", auto_adjust=True)
        if hist is None or len(hist) < 252:
            print(f"    ⚠️  {symbol} 歷史數據不足")
            return None, None
        info         = tk.info or {}
        trailing_eps = safe_float(info.get("trailingEps"))
        fcf          = safe_float(info.get("freeCashflow"))
        return hist, {"trailing_eps": trailing_eps, "fcf": fcf}
    except Exception as e:
        print(f"    ⚠️  {symbol} 抓取失敗：{e}")
        return None, None


# ── 指標計算 ────────────────────────────────────────────────

def add_indicators(df):
    """在 DataFrame 上計算所有回測需要的指標"""
    import pandas as pd
    df = df.copy()

    close  = df["Close"]
    volume = df["Volume"]

    # 52週滾動高點（252個交易日）
    df["roll_52w_high"]    = close.rolling(252, min_periods=60).max()
    df["pct_from_52w_high"] = (close / df["roll_52w_high"] - 1) * 100

    # 200日均線
    df["ma200"]           = close.rolling(200, min_periods=60).mean()
    df["pct_from_ma200"]  = (close / df["ma200"] - 1) * 100

    # 成交量倍數（近5日均量 / 近60日均量）
    df["vol_5d"]   = volume.rolling(5,  min_periods=1).mean()
    df["vol_60d"]  = volume.rolling(60, min_periods=20).mean()
    df["vol_ratio"] = df["vol_5d"] / df["vol_60d"].replace(0, np.nan)

    return df.dropna(subset=["ma200"])


# ── 訊號偵測 ────────────────────────────────────────────────

def find_signal_a(df, pe_mean, trailing_eps, is_etf=False) -> list:
    """
    訊號A：價值型逢低
    ① 距52週高點跌超過 20%
    ② PE 低於10年均值 15% 以上（ETF 或無數據則跳過PE條件）
    """
    # 條件①
    cond = df["pct_from_52w_high"] < SIGNAL_A_52W_DROP

    # 條件②（只有個股且有PE數據才加）
    if not is_etf and pe_mean and trailing_eps and trailing_eps > 0:
        pe_threshold    = pe_mean * (1 - SIGNAL_A_PE_DISCOUNT / 100)
        df["hist_pe"]   = df["Close"] / trailing_eps
        pe_cond         = (df["hist_pe"] > 0) & (df["hist_pe"] < pe_threshold)
        cond            = cond & pe_cond

    # 避免連續觸發（同一個下跌只算一次，間隔至少30天）
    raw_dates = df[cond].index.tolist()
    return _deduplicate_signals(raw_dates, min_gap=30)


def find_signal_b(df) -> list:
    """
    訊號B：技術反轉
    ① 距200日均線跌超過 15%
    ② 成交量放大 1.5 倍
    """
    cond = (
        (df["pct_from_ma200"] < SIGNAL_B_MA200_DROP) &
        (df["vol_ratio"] > SIGNAL_B_VOL_MULT)
    )
    raw_dates = df[cond].index.tolist()
    return _deduplicate_signals(raw_dates, min_gap=30)


def _deduplicate_signals(dates: list, min_gap: int = 30) -> list:
    """同一段下跌只取第一個訊號，避免重複計算"""
    if not dates:
        return []
    result   = [dates[0]]
    last_date = dates[0]
    for d in dates[1:]:
        gap = (d - last_date).days
        if gap >= min_gap:
            result.append(d)
            last_date = d
    return result


# ── 報酬計算 ────────────────────────────────────────────────

def calc_forward_returns(df, signal_dates: list) -> dict:
    """
    對每個訊號觸發日，計算 30/60/90 交易日後的報酬
    同時計算持有期間最大回撤
    """
    closes   = df["Close"]
    idx      = closes.index
    n        = len(closes)

    period_returns  = {d: [] for d in HOLDING_PERIODS}
    period_drawdowns = {d: [] for d in HOLDING_PERIODS}

    for entry_dt in signal_dates:
        try:
            entry_pos   = idx.get_loc(entry_dt)
            entry_price = closes.iloc[entry_pos]

            for days in HOLDING_PERIODS:
                exit_pos = entry_pos + days
                if exit_pos >= n:
                    continue

                exit_price = closes.iloc[exit_pos]
                ret        = (exit_price / entry_price - 1) * 100

                # 持有期間最大回撤
                window       = closes.iloc[entry_pos: exit_pos + 1]
                max_drawdown = ((window / entry_price) - 1).min() * 100

                period_returns[days].append(round(ret, 2))
                period_drawdowns[days].append(round(max_drawdown, 2))

        except Exception:
            continue

    return period_returns, period_drawdowns


# ── 統計計算 ────────────────────────────────────────────────

def compute_stats(returns: list, drawdowns: list) -> dict:
    """勝率、盈虧比、期望值、最大回撤"""
    if not returns:
        return None

    wins   = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate     = len(wins) / len(returns)
    avg_gain     = float(np.mean(wins))   if wins   else 0.0
    avg_loss     = float(np.mean(losses)) if losses else 0.0
    total_gain   = sum(wins)
    total_loss   = abs(sum(losses))
    profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else None
    expected_value = round(win_rate * avg_gain + (1 - win_rate) * avg_loss, 2)
    worst_drawdown = round(min(drawdowns), 1) if drawdowns else None

    return {
        "count":          len(returns),
        "win_rate":       round(win_rate * 100, 1),       # %
        "avg_gain":       round(avg_gain, 1),              # %
        "avg_loss":       round(avg_loss, 1),              # %
        "profit_factor":  profit_factor,                   # 總獲利/總虧損
        "expected_value": expected_value,                  # 期望值 %
        "worst_drawdown": worst_drawdown,                  # 持有期最大回撤 %
    }


# ── 主回測流程 ───────────────────────────────────────────────

def backtest_symbol(symbol: str, pe_cache: dict) -> dict | None:
    """對單一標的執行完整回測"""
    is_etf = symbol in ETF_SYMBOLS

    hist, info = fetch_history(symbol)
    if hist is None:
        return None

    df           = add_indicators(hist)
    pe_data      = pe_cache.get(symbol, {})
    pe_mean      = pe_data.get("pe_mean")
    trailing_eps = info.get("trailing_eps") if info else None
    fcf          = info.get("fcf") if info else None

    # ── 訊號A ──
    a_dates               = find_signal_a(df, pe_mean, trailing_eps, is_etf)
    a_returns, a_drawdowns = calc_forward_returns(df, a_dates)
    a_stats               = {d: compute_stats(a_returns[d], a_drawdowns[d])
                              for d in HOLDING_PERIODS}

    # ── 訊號B ──
    b_dates               = find_signal_b(df)
    b_returns, b_drawdowns = calc_forward_returns(df, b_dates)
    b_stats               = {d: compute_stats(b_returns[d], b_drawdowns[d])
                              for d in HOLDING_PERIODS}

    return {
        "symbol":       symbol,
        "is_etf":       is_etf,
        "pe_mean_10y":  pe_mean,
        "fcf_positive": fcf > 0 if fcf is not None else None,
        "data_range":   f"{str(df.index[0].date())} ~ {str(df.index[-1].date())}",
        "trading_days": len(df),
        "signal_a": {
            "name":       "價值型逢低",
            "conditions": f"距52週高點跌>{abs(SIGNAL_A_52W_DROP):.0f}%"
                          + (f" + PE低於{pe_mean:.0f}的{SIGNAL_A_PE_DISCOUNT:.0f}%"
                             if pe_mean else "（無PE條件）"),
            "trigger_count": len(a_dates),
            "last_triggers": [str(d.date()) for d in a_dates[-5:]],
            "stats":      {str(d): a_stats[d] for d in HOLDING_PERIODS},
        },
        "signal_b": {
            "name":       "技術反轉",
            "conditions": f"距200MA跌>{abs(SIGNAL_B_MA200_DROP):.0f}% + 量能>{SIGNAL_B_VOL_MULT}x",
            "trigger_count": len(b_dates),
            "last_triggers": [str(d.date()) for d in b_dates[-5:]],
            "stats":      {str(d): b_stats[d] for d in HOLDING_PERIODS},
        },
    }


def run_backtest(symbols: list = None) -> dict:
    """主函式：對觀察清單執行回測，結果存入 backtest_results.json"""
    print("\n【backtest.py】開始歷史回測（約需2–3分鐘）...")
    print(f"  訊號A：距52週高點跌>{abs(SIGNAL_A_52W_DROP):.0f}% + PE低於均值{SIGNAL_A_PE_DISCOUNT:.0f}%")
    print(f"  訊號B：距200MA跌>{abs(SIGNAL_B_MA200_DROP):.0f}% + 量能>{SIGNAL_B_VOL_MULT}x\n")

    if symbols is None:
        symbols = config.ALL_WATCHLIST  # 包含ETF，但訊號A的PE條件會自動跳過

    pe_cache = load_pe_cache()
    results  = {}

    for sym in symbols:
        print(f"  [{symbols.index(sym)+1:2d}/{len(symbols)}] {sym}...", end=" ")
        r = backtest_symbol(sym, pe_cache)
        if r:
            results[sym] = r
            a60 = r["signal_a"]["stats"].get("60")
            b60 = r["signal_b"]["stats"].get("60")
            a_str = f"A:{a60['win_rate']}%勝率" if a60 else "A:無觸發"
            b_str = f"B:{b60['win_rate']}%勝率" if b60 else "B:無觸發"
            print(f"{a_str}  {b_str}")
        else:
            print("跳過")

    output = {
        "generated":  str(date.today()),
        "parameters": {
            "signal_a_52w_drop":    SIGNAL_A_52W_DROP,
            "signal_a_pe_discount": SIGNAL_A_PE_DISCOUNT,
            "signal_b_ma200_drop":  SIGNAL_B_MA200_DROP,
            "signal_b_vol_mult":    SIGNAL_B_VOL_MULT,
            "holding_periods":      HOLDING_PERIODS,
        },
        "results": results,
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n【backtest.py】回測完成 ✅  共 {len(results)} 支標的")
    print(f"  結果已存至 backtest_results.json")
    return output


# ── 執行入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    output = run_backtest()

    print("\n" + "=" * 60)
    print("  回測結果摘要（60天持有期）")
    print("=" * 60)

    for sym, r in output["results"].items():
        print(f"\n  {sym}  （{r['data_range']}）")

        a = r["signal_a"]
        a60 = a["stats"].get("60")
        if a60 and a60["count"] > 0:
            ev_flag = "✅" if a60["expected_value"] > 0 else "❌"
            print(f"    訊號A（{a['name']}）觸發{a['trigger_count']}次")
            print(f"      60天勝率：{a60['win_rate']}%  "
                  f"均賺：{a60['avg_gain']}%  均虧：{a60['avg_loss']}%")
            print(f"      期望值：{ev_flag} {a60['expected_value']}%  "
                  f"最大回撤：{a60['worst_drawdown']}%")
        else:
            print(f"    訊號A：過去5年無觸發")

        b = r["signal_b"]
        b60 = b["stats"].get("60")
        if b60 and b60["count"] > 0:
            ev_flag = "✅" if b60["expected_value"] > 0 else "❌"
            print(f"    訊號B（{b['name']}）觸發{b['trigger_count']}次")
            print(f"      60天勝率：{b60['win_rate']}%  "
                  f"均賺：{b60['avg_gain']}%  均虧：{b60['avg_loss']}%")
            print(f"      期望值：{ev_flag} {b60['expected_value']}%  "
                  f"最大回撤：{b60['worst_drawdown']}%")
        else:
            print(f"    訊號B：過去5年無觸發")
