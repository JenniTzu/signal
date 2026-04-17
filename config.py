# ═══════════════════════════════════════════════════════════
# SIGNAL — 系統設定檔
# In the noise, find the signal.
# ═══════════════════════════════════════════════════════════

# ── API Keys ──────────────────────────────────────────────
# 安全做法：從系統環境變數讀取，不要把 Key 直接寫在這裡
import os as _os
ALPHA_VANTAGE_KEY = _os.environ.get("SIGNAL_AV_KEY",      "")
FRED_API_KEY      = _os.environ.get("SIGNAL_FRED_KEY",    "")
GEMINI_API_KEY    = _os.environ.get("SIGNAL_GEMINI_KEY",  "")
GITHUB_TOKEN      = _os.environ.get("SIGNAL_GITHUB_TOKEN","")
GITHUB_REPO       = "JenniTzu/signal"

# 如果環境變數沒設，也可以直接在下面填（本機測試用）：
# GITHUB_TOKEN = "ghp_..."

# ── 持股（含股數與成本價）────────────────────────────────────
HOLDINGS = {
    "QQQ":  {"cost": 487.92, "shares": 15, "category": "core",    "note": "核心ETF"},
    "SMH":  {"cost": 185.37, "shares": 15, "category": "holding", "note": "半導體ETF"},
    "NVDA": {"cost": 174.18, "shares": 2,  "category": "holding", "note": "持股"},
    "MSFT": {"cost": 409.00, "shares": 4,  "category": "holding", "note": "持股"},
    "TSLA": {"cost": 370.30, "shares": 2,  "category": "holding", "note": "持股"},
    "GOOG": {"cost": 309.10, "shares": 3,  "category": "holding", "note": "持股"},
}

# ── 逢低加碼目標股（霍華馬克斯視角：護城河寬 + 分散科技集中度）──
DIP_TARGETS = ["BRK-B", "V", "META", "ASML", "GOOG"]

# ── 波段潛力股 ──────────────────────────────────────────────
SWING_TARGETS = ["TSM", "PLTR"]

# ── 避險 ────────────────────────────────────────────────────
HEDGE = ["GLD"]

# ── 台股持股（含股數與成本價，幣別：新台幣）────────────────────
TW_HOLDINGS = {
    "0050.TW":   {"cost": 49.77,    "shares": 7000, "name": "元大台灣50",       "note": "核心ETF"},
    "00981A.TW": {"cost": 17.81,    "shares": 3000, "name": "主動統一台股增長", "note": "主動ETF"},
    "00988A.TW": {"cost": 10.89,    "shares": 2000, "name": "主動統一全球創新", "note": "主動ETF"},
    "2308.TW":   {"cost": 1056.85,  "shares": 13,   "name": "台達電",           "note": "持股"},
}

# ── 台股觀察清單（逢低加碼候選）────────────────────────────────
TW_WATCHLIST = ["2330.TW", "2454.TW", "2317.TW"]  # 台積電、聯發科、鴻海

# ── 產業 ETF ────────────────────────────────────────────────
SECTOR_ETFS = ["QQQ", "SMH", "XLF", "XLE", "GLD"]

# ── 市場指標 ────────────────────────────────────────────────
MARKET_INDICATORS = ["^VIX", "^TNX"]

# ── 部位管理設定 ────────────────────────────────────────────
TOTAL_CAPITAL_TWD   = 750000   # 總資金（台幣）
ADD_POSITION_PCT    = 0.05     # 每次加碼上限（總資金的 5%）
USD_TWD_RATE        = 31.5     # 美元兌台幣匯率（手動更新）

# 金字塔加碼比例
PYRAMID_LEVELS = [
    {"drop_pct": -0.10, "deploy_pct": 0.30, "label": "第一階 -10%"},
    {"drop_pct": -0.20, "deploy_pct": 0.30, "label": "第二階 -20%"},
    {"drop_pct": -0.30, "deploy_pct": 0.40, "label": "第三階 -30%"},
]

# 科技集中度警示閾值（QQQ + SMH + NVDA 合計佔比）
TECH_CONCENTRATION_WARN = 0.70  # > 70% 顯示紅色警告

# ── 觸發條件參數 ────────────────────────────────────────────
FGI_THRESHOLD           = 25     # Fear & Greed Index 極度恐慌閾值
VIX_THRESHOLD           = 30     # VIX 市場恐慌閾值
CREDIT_SPREAD_THRESHOLD = 500    # 信用利差觸發點（bps）

# 波段三燈條件
SWING_RSI_THRESHOLD     = 35     # RSI 超賣閾值
SWING_VOLUME_MULTIPLIER = 1.5    # 成交量放大倍數
SWING_PE_DISCOUNT       = 0.15   # 低於10年均值 15% 以上

# 動態掃描條件
DYNAMIC_MIN_MARKET_CAP  = 500e9  # 市值 > 500億美元（5百億，換算成美元）
DYNAMIC_PE_DISCOUNT     = 0.20   # 低於5年均值 20% 以上
DYNAMIC_RSI_MAX         = 35     # RSI 超賣
DYNAMIC_VOLUME_MULT     = 1.5    # 成交量放大倍數

# ── FOMC 會議日期 2026 ───────────────────────────────────────
FOMC_DATES_2026 = [
    "2026-01-28", "2026-01-29",
    "2026-03-18", "2026-03-19",
    "2026-05-06", "2026-05-07",
    "2026-06-17", "2026-06-18",
    "2026-07-29", "2026-07-30",
    "2026-09-16", "2026-09-17",
    "2026-10-28", "2026-10-29",
    "2026-12-09", "2026-12-10",
]

# ── S&P 100 股票清單 ─────────────────────────────────────────
SP100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "TSLA", "BRK-B",
    "UNH", "LLY", "JPM", "V", "XOM", "MA", "AVGO", "PG", "HD", "COST",
    "MRK", "CVX", "ABBV", "KO", "WMT", "BAC", "PEP", "ADBE", "CRM", "MCD",
    "ACN", "TMO", "CSCO", "ABT", "LIN", "DHR", "NFLX", "TMUS", "AMD", "CMCSA",
    "NKE", "INTC", "VZ", "TXN", "PM", "QCOM", "NEE", "UPS", "INTU", "COP",
    "RTX", "AMGN", "IBM", "HON", "GE", "LOW", "SPGI", "CAT", "SBUX", "GS",
    "BLK", "ELV", "MDT", "GILD", "DE", "ADP", "BKNG", "ISRG", "ADI", "MDLZ",
    "PLD", "CB", "AXP", "VRTX", "CVS", "REGN", "LRCX", "SYK", "MO", "ETN",
    "MMC", "ZTS", "BSX", "WFC", "NOC", "AON", "PGR", "SO", "F", "CME",
    "ATVI", "MSI", "TGT", "USB", "EMR", "MU", "TJX", "SCHW", "DUK", "ITW",
]

# ── FRED 指標代號 ────────────────────────────────────────────
FRED_HY_SPREAD_CODE = "BAMLH0A0HYM2"  # HY OAS 垃圾債利差

# ── 波段機會掃描標的（持股 + 逢低加碼 + 波段）────────────────
ALL_WATCHLIST = (
    list(HOLDINGS.keys()) +
    DIP_TARGETS +
    SWING_TARGETS +
    HEDGE
)
# 去重
ALL_WATCHLIST = list(dict.fromkeys(ALL_WATCHLIST))
