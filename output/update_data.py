# ═══════════════════════════════════════════════════════════
# SIGNAL — update_data.py
# 將當日分析結果寫入 docs/data.json（每天累積）
# ═══════════════════════════════════════════════════════════

import json
import os
import numpy as np
from datetime import datetime, timezone


class _SafeEncoder(json.JSONEncoder):
    """將 numpy/pandas 型態轉為 Python 原生型態"""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):  return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)):    return bool(obj)
        if isinstance(obj, (np.ndarray,)):  return obj.tolist()
        return super().default(obj)

_ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(_ROOT, "docs", "data.json")
MAX_HISTORY_DAYS = 365  # 最多保留一年


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8", errors="replace") as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass
    return {"history": []}


def save_data(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=_SafeEncoder)


def build_daily_record(
    date_str:        str,
    raw_data:        dict,
    signals:         dict,
    position_risk:   dict,
    dip_result:      dict,
    swing_result:    dict,
    dynamic_result:  dict,
    analyst_result:  dict,
    buffett_result:  dict,
    marks_result:    dict,
    pe_history:      dict,
) -> dict:
    """組合所有模組輸出，建立單日完整記錄"""

    fgi    = raw_data.get("fgi", {})
    market = raw_data.get("market", {})
    cs     = raw_data.get("credit_spread", {})
    vix    = market.get("vix", {})
    tnx    = market.get("tnx", {})

    # 市場環境
    from analysis.calculate import market_environment
    env = market_environment(
        fgi.get("score"),
        vix.get("value"),
        cs.get("value"),
    )

    # 三腦分歧分析
    divergence = _calc_divergence(
        analyst_result.get("per_stock", {}),
        buffett_result.get("per_stock", {}),
        marks_result.get("per_stock", {}),
    )

    # 組合當日摘要
    summary = _build_summary(
        env, dip_result, swing_result, marks_result, divergence
    )

    record = {
        "date":        date_str,
        "timestamp":   datetime.now(timezone.utc).isoformat(),

        # 市場溫度
        "market": {
            "fgi":           fgi.get("score"),
            "fgi_rating":    fgi.get("rating"),
            "fgi_history":   fgi.get("history", [])[-30:],
            "vix":           vix.get("value"),
            "vix_change":    vix.get("change"),
            "vix_history":   vix.get("history", [])[-30:],
            "tnx":           tnx.get("value"),
            "tnx_change":    tnx.get("change"),
            "credit_spread": cs.get("value"),
            "cs_history":    cs.get("history", [])[-30:],
            "environment":   env,
        },

        # 部位風險
        "position_risk": position_risk,

        # 產業ETF
        "sector_etfs": raw_data.get("sector_etfs", {}),

        # 個股完整數據
        "stocks": _clean_stocks(raw_data.get("stocks", {}), signals, pe_history),

        # 區塊一：逢低加碼雷達
        "dip_radar": dip_result,

        # 區塊二：波段掃描
        "swing": swing_result,

        # 區塊三：動態掃描
        "dynamic": dynamic_result,

        # 三腦分析
        "agents": {
            "analyst": {
                "per_stock": analyst_result.get("per_stock", {}),
                "source":    analyst_result.get("source", ""),
            },
            "buffett": {
                "per_stock": buffett_result.get("per_stock", {}),
                "source":    buffett_result.get("source", ""),
            },
            "marks": {
                "pendulum":  marks_result.get("pendulum", {}),
                "per_stock": marks_result.get("per_stock", {}),
                "source":    marks_result.get("source", ""),
            },
            "divergence": divergence,
        },

        # 今日操作總結
        "summary": summary,
    }

    return record


def _clean_stocks(stocks: dict, signals: dict, pe_history: dict) -> dict:
    """整合個股數據 + 技術訊號 + 歷史PE，清理不必要欄位"""
    cleaned = {}
    for sym, s in stocks.items():
        sig = signals.get(sym, {})
        pe  = pe_history.get(sym, {})
        merged = {**s, **{
            "rsi_label":   sig.get("rsi_label"),
            "vol_label":   sig.get("vol_label"),
            "ma200_label": sig.get("ma200_label"),
            "pct_from_cost": sig.get("pct_from_cost"),
            "pe_mean_10y": pe.get("pe_mean"),
            "pe_25pct":    pe.get("pe_25pct"),
            "pe_75pct":    pe.get("pe_75pct"),
            "pe_source":   pe.get("source"),
        }}
        # 移除超大欄位，保留必要數據
        merged.pop("error", None)
        cleaned[sym] = merged
    return cleaned


def _calc_divergence(analyst_ps, buffett_ps, marks_ps) -> dict:
    """計算三腦分歧程度"""
    symbols = set(analyst_ps) | set(buffett_ps) | set(marks_ps)
    agreements = 0
    total = 0

    def to_score(status):
        if status in ("🟢", "✅"):  return 1
        if status in ("🟡", "⚠️"): return 0
        if status in ("🔴", "❌"): return -1
        return None

    for sym in symbols:
        a = to_score(analyst_ps.get(sym, {}).get("status"))
        b = to_score(buffett_ps.get(sym, {}).get("status"))
        m = to_score(marks_ps.get(sym,  {}).get("status"))
        vals = [v for v in [a, b, m] if v is not None]
        if len(vals) >= 2:
            total += 1
            if max(vals) - min(vals) <= 1:
                agreements += 1

    consensus_pct = round(agreements / total * 100) if total > 0 else 0
    has_divergence = consensus_pct < 60

    return {
        "consensus_pct": consensus_pct,
        "has_divergence": has_divergence,
        "label": "⚡ 三腦出現分歧，請自行判斷" if has_divergence else "三腦方向一致",
    }


def _build_summary(env, dip_result, swing_result, marks_result, divergence) -> str:
    """產生今日操作總結（150字以內）"""
    parts = []

    # 市場環境
    parts.append(f"市場環境：{env['emoji']}{env['label']}。")

    # 逢低加碼雷達
    triggers = dip_result.get("triggers", {})
    if triggers.get("radar_active"):
        parts.append(f"逢低加碼雷達啟動（{triggers.get('triggered_count')}/3條件成立）。")
    else:
        parts.append(f"逢低加碼雷達待機（{triggers.get('triggered_count', 0)}/3條件）。")

    # 波段全綠
    all_green = swing_result.get("all_green_list", [])
    if all_green:
        parts.append(f"波段三燈全綠：{', '.join(all_green)}。")
    else:
        parts.append("目前無波段三燈全綠標的。")

    # 市場鐘擺
    pend = marks_result.get("pendulum", {})
    if pend:
        parts.append(f"市場鐘擺：{pend.get('label', 'N/A')}。")

    # 分歧
    parts.append(divergence.get("label", ""))

    return " ".join(p for p in parts if p)[:200]


def append_daily_record(record: dict):
    """將單日記錄追加到 data.json"""
    data = load_data()
    history = data.get("history", [])

    # 更新同日記錄
    existing = [i for i, r in enumerate(history) if r.get("date") == record["date"]]
    if existing:
        history[existing[0]] = record
        print(f"  更新既有記錄：{record['date']}")
    else:
        history.append(record)
        print(f"  新增記錄：{record['date']}")

    # 裁剪舊資料
    if len(history) > MAX_HISTORY_DAYS:
        history = history[-MAX_HISTORY_DAYS:]

    data["history"] = history
    # 最新記錄也放在頂層方便前端快速讀取
    data["latest"]  = record
    data["updated"] = datetime.now(timezone.utc).isoformat()

    save_data(data)
    print(f"  data.json 已更新（共 {len(history)} 筆記錄）✅")


def run_update(date_str, raw_data, signals, position_risk, dip_result,
               swing_result, dynamic_result, analyst_result,
               buffett_result, marks_result, pe_history):
    """主函式"""
    print("\n【update_data.py】寫入 data.json...")
    record = build_daily_record(
        date_str, raw_data, signals, position_risk,
        dip_result, swing_result, dynamic_result,
        analyst_result, buffett_result, marks_result, pe_history
    )
    append_daily_record(record)
    return record
