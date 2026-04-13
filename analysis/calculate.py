# ═══════════════════════════════════════════════════════════
# SIGNAL — calculate.py
# 技術指標計算、市場環境標籤
# ═══════════════════════════════════════════════════════════

import pandas as pd
import config


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """計算 RSI-14"""
    if len(prices) < period + 1:
        return None
    delta    = prices.diff().dropna()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def label_rsi(rsi: float | None) -> str:
    if rsi is None:
        return "N/A"
    if rsi < 30:
        return "超賣"
    if rsi < 40:
        return "偏低"
    if rsi < 60:
        return "中性"
    if rsi < 70:
        return "偏高"
    return "超買"


def label_vol_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "N/A"
    if ratio >= 2.0:
        return "爆量"
    if ratio >= 1.5:
        return "放量"
    if ratio >= 0.8:
        return "正常"
    return "縮量"


def label_ma200_deviation(pct: float | None) -> str:
    if pct is None:
        return "N/A"
    if pct > 30:
        return "嚴重偏高"
    if pct > 10:
        return "偏高"
    if pct > -10:
        return "均線附近"
    if pct > -20:
        return "偏低"
    return "嚴重偏低"


def market_environment(fgi_score, vix_value, credit_spread_bps) -> dict:
    """
    根據 FGI / VIX / 信用利差 判斷市場環境
    回傳 { label, color, emoji }
    """
    risk_off_count = 0
    risk_on_count  = 0

    if fgi_score is not None:
        if fgi_score < 30:
            risk_off_count += 1
        elif fgi_score > 65:
            risk_on_count += 1

    if vix_value is not None:
        if vix_value > 25:
            risk_off_count += 1
        elif vix_value < 15:
            risk_on_count += 1

    if credit_spread_bps is not None:
        if credit_spread_bps > 500:
            risk_off_count += 1
        elif credit_spread_bps < 300:
            risk_on_count += 1

    if risk_off_count >= 2:
        return {"label": "Risk-Off", "color": "red",    "emoji": "🔴"}
    if risk_on_count >= 2:
        return {"label": "Risk-On",  "color": "green",  "emoji": "🟢"}
    return     {"label": "Neutral",  "color": "yellow", "emoji": "🟡"}


def calc_stock_signals(stock: dict) -> dict:
    """
    為單一股票計算所有衍生訊號標籤
    輸入：fetch_data 的 stock dict
    回傳：加入各種 label 的新 dict
    """
    s = dict(stock)

    s["rsi_label"]    = label_rsi(s.get("rsi14"))
    s["vol_label"]    = label_vol_ratio(s.get("vol_ratio"))
    s["ma200_label"]  = label_ma200_deviation(s.get("pct_from_ma200"))

    # 是否超賣反轉訊號（RSI < 35 且成交量放大）
    rsi = s.get("rsi14")
    vol = s.get("vol_ratio")
    s["oversold_signal"] = bool(
        rsi is not None and rsi < config.SWING_RSI_THRESHOLD
        and vol is not None and vol >= config.SWING_VOLUME_MULTIPLIER
    )

    # 距持股成本 %
    holding = config.HOLDINGS.get(s["symbol"])
    if holding and holding.get("cost") and s.get("price"):
        s["pct_from_cost"] = round((s["price"] / holding["cost"] - 1) * 100, 2)
    else:
        s["pct_from_cost"] = None

    return s


def calc_all_signals(stocks: dict) -> dict:
    """對所有股票跑 calc_stock_signals"""
    return {sym: calc_stock_signals(stock) for sym, stock in stocks.items()}
