# SIGNAL — Claude Code 工作手冊
> In the noise, find the signal.
> 這份文件是給 Claude Code 讀的，讓它每次進入專案時都能立刻理解背景。

---

## 系統簡介

SIGNAL 是一套全自動每日投資監控系統。
每天台灣時間早上 08:00 自動執行，抓取市場數據，
透過三個 AI Agent 從不同視角分析，
將結果更新到 GitHub Pages 網站，資料每天累積。

使用者：Jennifer（無程式背景，請全程用繁體中文溝通）
投資風格：價值投資 + 逢低加碼 + 波段操作
核心理念：三個 Agent 觀點可以不同，矛盾本身就是資訊

---

## 重要原則

1. 所有說明、錯誤訊息、提問，請用繁體中文
2. 遇到錯誤請自動修正，不要問使用者技術問題
3. 每個步驟完成後，停下來讓使用者確認再繼續
4. API Key 如果是空字串 ""，跳過該功能不要報錯
5. 不要更動 config.py 的結構，只能修改數值

---

## 專案結構

```
SIGNAL/
├── CLAUDE.md               ← 你現在讀的這份文件
├── config.py               ← 所有參數集中管理（不要改結構）
├── main.py                 ← 主程式，串接所有模組
├── run_signal.bat          ← 排程執行腳本（含 API Key，不推送到 GitHub）
│
├── data/                   ← 資料抓取層
│   ├── fetch_data.py       ← yfinance + fear-greed + FRED 數據抓取
│   └── fetch_history.py    ← Alpha Vantage / yfinance 歷史本益比計算（有快取）
│
├── analysis/               ← 分析計算層
│   ├── calculate.py        ← RSI、均線、成交量等技術指標計算
│   ├── position_manager.py ← 部位風險計算（集中度、子彈、壓力測試）
│   ├── dip_radar.py        ← 區塊一：逢低加碼雷達
│   ├── swing_scanner.py    ← 區塊二：波段三燈掃描
│   ├── dynamic_scanner.py  ← 區塊三：S&P100 動態機會掃描
│   └── backtest.py         ← 歷史回測模組（訊號A價值型/訊號B技術型）
│
├── agents/                 ← AI Agent 層
│   ├── analyst_agent.py    ← Agent 1：策略分析師（技術面時機判斷）
│   ├── buffett_agent.py    ← Agent 2：巴菲特大腦（基本面品質鑑定）
│   └── howard_marks_agent.py ← Agent 3：霍華馬克斯大腦（週期風險評估）
│
├── output/                 ← 輸出層
│   ├── update_data.py      ← 將當日結果寫入 docs/data.json
│   └── deploy.py           ← git push 推送到 GitHub Pages
│
├── cache/                  ← 快取與執行記錄（不推送 GitHub）
│   ├── pe_history_cache.json    ← 歷史本益比快取（自動產生）
│   ├── backtest_results.json    ← 回測結果快取（手動執行 --backtest 產生）
│   └── run_log.txt              ← 每日排程執行記錄
│
├── scripts/                ← 工具腳本（不推送 GitHub）
│   ├── setup_scheduler.bat ← Windows 工作排程器設定
│   └── setup_scheduler.ps1 ← PowerShell 版工作排程器設定（需管理員執行）
│
└── docs/                   ← GitHub Pages 網站根目錄
    ├── index.html          ← 網站主頁（含所有視覺化 + 回測統計）
    ├── data.json           ← 累積歷史資料（每天更新）
    └── backtest.json       ← 回測結果（每次執行 --backtest 後自動複製）
```

---

## 投資組合

```
# 從 config.py 讀取，不要硬編碼

持股（雙邏輯：技術面 + 基本面同時分析）：
  NVDA  成本 $177
  SMH   成本 $210
  QQQ   核心定期定額（不設成本價）

逢低加碼目標股：
  GOOGL, MSFT, V, BRK-B, VTI, ASML, AMD

波段潛力股：
  TSM, PLTR

避險：
  GLD
```

---

## 資料來源

| 資料 | 來源 | 備註 |
|------|------|------|
| 即時股價、RSI、均線、成交量、新聞 | yfinance | 主要來源 |
| 10年歷史本益比計算 | Alpha Vantage + yfinance fallback | 有快取，每次跳過已計算標的 |
| CNN Fear & Greed Index | fear-greed 套件 | pip install fear-greed |
| HY OAS Credit Spread | FRED API | 代號 BAMLH0A0HYM2，需 FRED_API_KEY |
| FOMC 日期 | config.py 手動填入 | 2026 全年已填好 |
| S&P100 動態掃描 | yfinance | 清單在 config.py SP100 |

---

## 三個 Agent 的分工（非常重要）

### Agent 1：策略分析師
- 角色：時機判斷者
- 核心問題：「現在按下扳機的時機對嗎？」
- 只看：RSI、成交量、200日均線、產業ETF資金流向
- 不看：基本面、估值（這是關鍵區別）
- 輸出：🟢時機到 / 🟡訊號出現中 / 🔴尚未到位 + 一句話

### Agent 2：巴菲特大腦
- 角色：企業本質鑑定者
- 核心問題：「這家公司值得長期擁有嗎？」
- 只看：護城河、毛利率趨勢、ROE、FCF、管理層行為、新聞
- 不看：RSI、技術面（這是關鍵區別）
- 輸出：✅護城河穩固 / ⚠️需觀察 / ❌基本面惡化 + 一句話

### Agent 3：霍華馬克斯大腦
- 角色：風險與週期評估者
- 核心問題：「這個價格的風險合理嗎？」
- 只看：Credit Spread、FGI趨勢、VIX方向、個股歷史本益比區間
- 不看：RSI、技術面（這是關鍵區別）
- 輸出：鐘擺位置 + 個股🟢🟡🔴 + 一句話

⚠️ 三個 Agent 優先使用 Gemini API（gemini-1.5-flash 免費 tier）
⚠️ 若 GEMINI_API_KEY 未設定，自動切換為內建規則引擎（功能完整，無 AI 語言）
⚠️ 三個 Agent 結論可以互相矛盾，這是設計，不是 bug

---

## 三大核心區塊

### 區塊一：逢低加碼雷達
觸發條件（三選二）：
- FGI < 25（config.py FGI_THRESHOLD）
- VIX > 30（config.py VIX_THRESHOLD）
- Credit Spread > 500bps（config.py CREDIT_SPREAD_THRESHOLD）

金字塔加碼：-10%加30%、-20%再加30%、-30%再加40%
每個條件旁邊要有 ⓘ 說明文字（前端顯示）

### 區塊二：波段機會掃描
三燈全綠才標註「今日最強訊號」：
- 巴菲特燈：FCF為正 + ROE > 15% + 毛利率未惡化（3選2=黃、3全中=綠）
- 馬克斯燈：本益比低於10年均值15%以上
- 技術燈：RSI < 35 反轉 + 成交量放大1.5倍

NVDA 特殊：並排顯示持股邏輯 + 波段三燈

### 區塊三：動態機會掃描（S&P100）
五個條件全部符合才出現：
① 市值 > 500億美元
② 本益比低於5年均值20%以上
③ RSI < 35 開始反轉
④ 近5日成交量 > 60日均量1.5倍
⑤ FCF 為正

無結果時顯示：「今日無訊號，繼續等待是最好的策略」

---

## 網站設計規格

```
風格：深色主題 #0D1117
強調色：綠 #00FF94 / 黃 #FFD700 / 紅 #FF4444
字型：系統內建中文字型
圖表：Chart.js（CDN 引入）
```

頁面區塊順序：
1. 標題列（SIGNAL + 日期 + 歷史日期選擇器）
2. 🚨 部位風險警示（集中度/損失估計/子彈/財報天數/FOMC天數）
3. 市場溫度（FGI大字儀表板 + VIX + 美債 + Credit Spread）
4. 歷史趨勢圖（FGI + VIX + Credit Spread 三圖30日）
5. 區塊一：逢低加碼雷達（含 ⓘ 說明）
6. 區塊二：波段機會掃描（含 ⓘ 說明）
7. 區塊三：動態機會掃描
8. 三腦會議（三欄並排 + 共識進度條）
9. 個股歷史圖（點選標的看30天走勢）
10. 風險預警（✅/⚠️ + 新聞摘要）
11. 今日操作總結（150字 + 時間戳記）

---

## 部位管理

```
總資金：750,000 台幣（config.py TOTAL_CAPITAL_TWD）
匯率：31.5 TWD/USD（config.py USD_TWD_RATE，需手動更新）
每次加碼上限：總資金 5%（約 3.5 萬台幣）
集中度警示閾值：70%（NVDA + SMH + QQQ）
```

每日計算並顯示：
- 科技集中度 %（> 70% 顯示紅色警告）
- 若市場跌20%，預估損失多少台幣
- 今日可用子彈還剩多少

⚠️ 集中度計算使用固定比例估算（QQQ=20%、NVDA/SMH各25%），
   非實際持倉數量，僅供參考方向。

---

## data.json 格式

實際結構為三個頂層 key：

```json
{
  "history": [
    {
      "date": "2026-03-30",
      "timestamp": "2026-03-30T00:30:00+00:00",
      "market": {
        "fgi": 18,
        "fgi_rating": "Extreme Fear",
        "fgi_history": [...],
        "vix": 32.5,
        "vix_change": -1.2,
        "vix_history": [...],
        "tnx": 4.38,
        "tnx_change": 0.02,
        "credit_spread": 520,
        "cs_history": [...],
        "environment": {"label": "Risk-Off", "color": "red", "emoji": "🔴"}
      },
      "position_risk": {
        "tech_concentration": {...},
        "drawdown_20pct": {...},
        "bullets": {...},
        "fomc": {"date": "2026-05-06", "days": 12},
        "next_earnings": {"symbol": "NVDA", "date": "2026-05-28", "days": 8},
        "pyramid_status": {...}
      },
      "sector_etfs": {"QQQ": {...}, "SMH": {...}, ...},
      "stocks": {"NVDA": {...}, "GOOGL": {...}, ...},
      "dip_radar": {"triggers": {...}, "dip_targets": [...]},
      "swing": {"swing_results": [...], "nvda_special": {...}, "all_green_list": []},
      "dynamic": {"results": [...], "summary": "...", "scanned": 93, "hits": 0},
      "agents": {
        "analyst": {"per_stock": {...}, "source": "rule_engine"},
        "buffett":  {"per_stock": {...}, "source": "rule_engine"},
        "marks":    {"pendulum": {...}, "per_stock": {...}, "source": "rule_engine"},
        "divergence": {"consensus_pct": 75, "has_divergence": false, "label": "..."}
      },
      "summary": "今日操作總結文字..."
    }
  ],
  "latest": { ...同上單日結構... },
  "updated": "2026-04-13T00:35:00.000000+00:00"
}
```

- `history`：陣列，最多保留 365 筆（`MAX_HISTORY_DAYS`），最舊在前
- `latest`：最新一筆的完整副本，前端快速讀取用
- `updated`：最後寫入的 UTC 時間戳

---

## 執行流程

```
main.py 執行順序：
1. fetch_data.py         → 抓即時數據（stocks / market / fgi / credit_spread / sector_etfs）
2. fetch_history.py      → 歷史本益比（有快取則直接用，AV Key 空則 yfinance fallback）
3. calculate.py          → 計算技術指標標籤（rsi_label / vol_label / ma200_label）
4. position_manager.py   → 計算部位風險（集中度 / 子彈 / FOMC / 財報 / 金字塔）
5. dip_radar.py          → 逢低加碼雷達判斷（三選二觸發）
6. swing_scanner.py      → 波段三燈判斷（巴菲特燈 / 馬克斯燈 / 技術燈）
7. dynamic_scanner.py    → S&P100 動態掃描（可用 --skip-dynamic 跳過）
8. analyst_agent.py      → 策略分析師（Gemini 或規則引擎）
9. buffett_agent.py      → 巴菲特大腦（Gemini 或規則引擎）
10. howard_marks_agent.py → 霍華馬克斯大腦（Gemini 或規則引擎）
11. update_data.py        → 寫入 docs/data.json
12. deploy.py             → 推送 GitHub Pages
```

main.py 支援的執行參數：
- `--skip-dynamic`：跳過 S&P100 掃描（省時，測試用）
- `--dry-run`：執行到 update_data 但不 deploy
- `--skip-deploy`：同 dry-run
- `--force-pe`：強制重新抓歷史本益比（忽略快取）
- `--backtest`：執行歷史回測（獨立模式，不跑每日分析），結果存到 cache/backtest_results.json

---

## 自動排程

- 工具：Windows 工作排程器（Task Scheduler）
- 排程腳本：`run_signal.bat`（含 API Key，不推送 GitHub）
- 執行時間：每天早上 08:00
- 補跑機制：`StartWhenAvailable = True`，若 08:00 未開機，開機後自動補執行
- 設定方式：以管理員身分執行 `setup_scheduler.ps1`（一次性設定）
- 排程名稱：`SIGNAL_Daily`（可在工作排程器查看）

⚠️ 系統不會自動跳過週末或假日，若不想產生空資料，關機即可。

---

## 已知限制

| 項目 | 限制 | 處理方式 |
|------|------|---------|
| Alpha Vantage 免費版 | 每分鐘5次請求 | 批次抓取 + 每次等12秒 delay |
| 歷史本益比 | 非直接提供，需計算 | fetch_history.py 計算，結果快取到 pe_history_cache.json |
| 集中度計算 | 無實際持倉數量 | 固定比例估算，僅供方向參考 |
| FOMC 日期 | yfinance 無提供 | config.py 手動填入，2026 全年已設好 |
| Credit Spread | 需 FRED API Key | 未設定時顯示「待設定」，不影響其他功能 |

---

## 常見問題處理

**API Key 是空的：**
→ 跳過該功能，在網站顯示「待設定」，其他功能正常繼續

**yfinance 抓取失敗：**
→ 記錄 error 欄位，跳過該股，不中斷整體流程（無 retry）

**Gemini API 失敗或 Key 未設定：**
→ 自動切換為內建規則引擎，分析結果仍完整，source 標記為 "rule_engine"

**data.json 不存在：**
→ load_data() 自動回傳 {"history": []}，save_data() 自動建立檔案

**排程執行但沒有更新網站：**
→ 查看 run_log.txt 最後一行的 exit code，若非 0 代表失敗
→ 用管理員身分在工作排程器手動觸發，觀察輸出

---

## 給 Claude Code 的提醒

- 使用者不懂程式，所有輸出請用繁體中文
- 每個步驟做完請印出結果讓使用者確認
- 不要自作主張跳步驟
- 遇到技術問題自己解決，不要問使用者
- config.py 是唯一需要使用者手動修改的檔案
- run_signal.bat 含有 API Key，確認不要被 git add 進去
- cache/ 和 scripts/ 資料夾不推送到 GitHub（在 .gitignore 或手動排除）
- 各子資料夾都有 `__init__.py`，讓 Python 把它們當套件（package）處理
- 子資料夾內的模組互相引用時用相對 import（如 from .calculate import compute_rsi）
- deploy.py 部署時會自動把 cache/backtest_results.json 複製到 docs/backtest.json
