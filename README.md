# STRUCT.ai

> A real-time Smart Money Concepts (SMC) market structure analysis and trading dashboard, bridged directly to MetaTrader 5.

STRUCT.ai connects to your live MetaTrader 5 terminal, runs a suite of rule-based market analysis engines on live OHLC data, and serves everything through a modern React dashboard — giving you professional-grade market structure analysis in your browser in real time.

---

## What It Does

STRUCT.ai is **not** a simple chart wrapper. It implements a full algorithmic market structure pipeline:

- Detects swing highs/lows using fractal logic (ZigZag)
- Classifies market structure: HH, HL, LH, LL, EQH, EQL
- Determines trend on every timeframe (bullish / bearish / neutral)
- Detects Break of Structure (BOS) and Change of Character (CHoCH) events
- Identifies supply/demand zones and multi-timeframe S/R levels with recency scoring
- Computes trendlines, Fibonacci retracements, and session boxes (Asia / London / NY)
- Generates plain-English market narrative from all the above
- Checks trade readiness against a structured framework (SCALP or LIMIT)
- Integrates live news impact blocking per currency pair
- Supports direct order execution (MARKET and LIMIT) via MT5 bridge

---

## Architecture

```
MetaTrader 5 Terminal (Windows)
         │
         ▼
  mt5_bridge.py
  Polls MT5 every few seconds → pushes OHLC candles to the API
         │
         ▼
  FastAPI Backend  (localhost:8001)
  Runs all analysis engines on the candle data
  Exposes REST endpoints + WebSocket for live updates
         │
         ▼
  React Dashboard  (localhost:5173)
  Renders charts, overlays, narrative, trade panel
  Re-fetches automatically on every new candle via WebSocket
```

---

## Analysis Engines

All engines live in `artifacts/trading-api/services/`. They are pure computation — no ML, no black box, all rule-based and readable.

| Engine | File | What it does |
|---|---|---|
| **ZigZag** | `zigzag_engine.py` | Detects swing highs/lows using fractal logic (N bars on each side). Enforces strict alternation: High → Low → High → Low. |
| **Structure** | `structure_engine.py` | Classifies each confirmed swing as HH, HL, LH, LL, EQH, or EQL based on comparison with the previous swing of the same kind. |
| **Trend** | `trend_engine.py` | Reads the most recent structure labels and calls trend: bullish (HH+HL), bearish (LH+LL), or neutral (mixed). |
| **BOS** | `bos_engine.py` | Break of Structure — detects when a candle CLOSES beyond a confirmed swing high or low, filtered by current trend direction. |
| **CHoCH** | `choch_engine.py` | Change of Character — detects the first reversal signal: a close below the most recent HL (in bullish trend) or above the most recent LH (in bearish trend). |
| **Zones** | `zones_engine.py` | Detects supply/demand zones by clustering swing points within a pip threshold. Zones with 2+ touches are valid. Pip-size-aware (JPY vs non-JPY). |
| **MTF S/R** | `mtf_sr_engine.py` | Multi-timeframe support/resistance. Clusters swing levels across 15m, 1h, 4h. Scores levels by recency using exponential decay. Applies S/R flip based on price position. |
| **Trendline** | `trendline_engine.py` | Computes bullish and bearish trendlines from swing points. |
| **Session** | `session_engine.py` | Marks Asian, London, and New York session boxes on the chart. |
| **Narrative** | `narrative_engine.py` | Takes all computed data (bias, BOS, CHoCH, zones, S/R, sessions) and produces plain-English market commentary: condition, structure summary, key levels, trade readiness, confidence score. |
| **Framework Checker** | `framework_checker.py` | Walks a SCALP or LIMIT checklist against live data. Returns step-by-step pass/fail for each condition. |

---

## API Routes

The FastAPI backend runs at `http://localhost:8001` with prefix `/trading-api`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/trading-api/health` | Health check |
| `GET` | `/trading-api/structure` | Full market structure analysis for a symbol + timeframe |
| `GET` | `/trading-api/narrative` | Plain-English narrative (multi-timeframe: 5m, 15m, 1h, 4h) |
| `GET` | `/trading-api/sr-levels` | Multi-timeframe S/R levels (scored, recency-weighted) |
| `GET` | `/trading-api/mtf-bias` | Multi-timeframe trend bias |
| `GET` | `/trading-api/sessions` | Current session boxes |
| `GET` | `/trading-api/broker-time` | Broker server timestamp |
| `GET` | `/trading-api/daily-pnl` | Today's P&L, trade count, and win count from MT5 history |
| `GET` | `/trading-api/news-status` | News impact status per pair (blocked / caution / clear) |
| `POST` | `/trading-api/mt5/push` | MT5 bridge pushes OHLC candles here |
| `GET` | `/trading-api/mt5/status` | MT5 connection status |
| `POST` | `/trading-api/trade/open` | Submit a trade order |
| `POST` | `/trading-api/trade/close` | Close an open position |
| `GET` | `/trading-api/trade/poll` | Bridge polls for pending orders |
| `POST` | `/trading-api/trade/result` | Bridge posts execution result |
| `WebSocket` | `/trading-api/ws` | Real-time candle push to the dashboard |

Full interactive docs: `http://localhost:8001/docs`

---

## Dashboard Pages

### Main Dashboard (`/`)

The primary trading view. Contains:

- **TradingChart** — Candlestick chart (lightweight-charts). Toggle overlays on/off:
  - ZigZag swing lines and HH/HL/LH/LL labels
  - BOS and CHoCH markers
  - Supply/Demand zones (red/green rectangles)
  - Multi-timeframe S/R levels (15m, 1h, 4h, D1)
  - Session boxes (Asia, London, NY)
  - Order Blocks (OB)
  - Fair Value Gaps (FVG)
  - Fibonacci retracement (4H and D1 swing)
  - SL/TP lines from the trade panel
- **TopBar** — Symbol selector (7 pairs), timeframe selector (5m, 15m, 1h, 4h, D1), live trend badges per timeframe
- **TradePanel** — Order entry: BUY/SELL, MARKET/LIMIT, lot size, SL/TP with live pip/risk calculator, position list, one-click close and breakeven
- **MarketNarrative** — Auto-refreshing plain-English commentary: market condition, structure summary, key levels, trade readiness checklist, confidence score
- **HeatmapSidebar** — Currency pair heatmap
- **NewsPanel** — News impact status (blocked / caution / clear) per pair

### Analysis Page (`/analysis`)

Full-width deep-dive view. Left panel: market narrative. Right panel: FrameworkPanel — step-by-step SCALP or LIMIT framework checker with live pass/fail for each condition, stale-price guards, and invalidation detection.

---

## Supported Symbols & Timeframes

**Symbols:** USD/JPY · EUR/USD · GBP/USD · AUD/USD · USD/CHF · EUR/JPY · GBP/JPY

**Timeframes:** 5m · 15m · 1h · 4h · D1

---

## Tech Stack

| Layer | Technology |
|---|---|
| Trading terminal | MetaTrader 5 (Windows only) |
| MT5 bridge | Python, `MetaTrader5` package |
| Backend API | Python 3.12, FastAPI, Uvicorn |
| Data processing | pandas, numpy |
| HTTP / async | httpx, websockets |
| Frontend | React 18, TypeScript, Vite |
| Charts | lightweight-charts |
| State / data fetching | TanStack React Query |
| Routing | Wouter |
| UI components | Tailwind CSS, shadcn/ui |
| Monorepo | pnpm workspaces |

---

## Prerequisites

- **Windows machine** — the `MetaTrader5` Python package is Windows-only
- **MetaTrader 5** installed and logged in (demo or live account)
- **Python 3.10+** on your PATH
- **Node.js 18+** and **pnpm** installed

---

## Quick Start

### Option A — One-click (Windows)

Double-click `STRUCT-AI.bat`. It will install all dependencies, start all three services, and open the dashboard automatically.

### Option B — Manual

**1. Install Python dependencies**

```bash
pip install fastapi "uvicorn[standard]" pandas numpy httpx websockets python-dotenv requests MetaTrader5
```

**2. Install frontend dependencies**

```bash
pnpm install
```

**3. Start the trading API**

```bash
cd artifacts/trading-api
python main.py
```

Wait until the terminal prints that the server is running.

**4. Start the MT5 bridge**

```bash
python artifacts/trading-api/mt5-bridge/mt5_bridge.py
```

**5. Start the dashboard**

```bash
pnpm --filter @workspace/trading-dashboard run dev
```

**6. Open the dashboard**

```
http://localhost:5173
```

---

## Service URLs

| Service | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| Trading API | http://localhost:8001 |
| API Interactive Docs | http://localhost:8001/docs |
| WebSocket | ws://localhost:8001/trading-api/ws |

---

## How the MT5 Bridge Works

`mt5_bridge.py` uses the official `MetaTrader5` Python package to connect directly to the MT5 terminal running on the same Windows machine. On each tick:

1. It fetches OHLC candles for each configured symbol and timeframe
2. Posts them to `POST /trading-api/mt5/push`
3. The backend stores them in memory and broadcasts a WebSocket message to all connected dashboard clients
4. The dashboard re-fetches the analysis instantly on receipt

For trade execution, the bridge polls `GET /trading-api/trade/poll`, executes any pending orders on MT5, and posts results back to `POST /trading-api/trade/result`.

---

## How the Analysis Pipeline Works

For each request to `/trading-api/structure?symbol=USD/JPY&interval=5m`:

```
1. fetch_ohlc()           → Load candle data (from MT5 store or external feed)
2. detect_swings()        → ZigZag fractal swing detection
3. classify_structure()   → Label each swing HH/HL/LH/LL/EQH/EQL
4. detect_trend()         → Bullish / bearish / neutral from most recent labels
5. detect_bos()           → Break of Structure events
6. detect_choch()         → Change of Character events
7. compute_trendlines()   → Bullish and bearish trendlines
8. detect_zones()         → Supply/demand zone rectangles
9. compute_mtf_sr_levels()→ Multi-timeframe S/R with recency scoring
10. compute_sessions()    → Session boxes (Asia, London, NY)
11. cache_result()        → Cache the result to avoid redundant recomputation
12. return JSON           → All of the above in one response
```

The narrative endpoint runs this pipeline across 5m, 15m, 1h, and 4h concurrently, then passes all results to `generate_narrative()` to produce the plain-English summary.

---

## Project Structure

```
STRUCT.ai/
├── START_HERE.bat                        # Quick-start instructions
├── STRUCT-AI.bat                         # Full automated setup & launch
├── start_api.bat                         # Start API only
├── start_bridge.bat                      # Start MT5 bridge only
│
├── artifacts/
│   ├── trading-api/                      # Python FastAPI backend
│   │   ├── main.py                       # App entry point, router registration, WebSocket
│   │   ├── ws_manager.py                 # WebSocket broadcast manager
│   │   ├── requirements.txt              # Python dependencies
│   │   ├── routers/
│   │   │   ├── structure.py              # Full structure analysis endpoint
│   │   │   ├── narrative.py              # Plain-English narrative endpoint
│   │   │   ├── trading.py                # Trade order execution
│   │   │   ├── mt5.py                    # MT5 bridge push + status
│   │   │   ├── news.py                   # News impact proxy
│   │   │   ├── daily_pnl.py             # Daily P&L from MT5
│   │   │   └── data.py                   # OHLC data endpoint
│   │   ├── services/
│   │   │   ├── zigzag_engine.py          # Fractal swing detection
│   │   │   ├── structure_engine.py       # HH/HL/LH/LL classification
│   │   │   ├── trend_engine.py           # Trend determination
│   │   │   ├── bos_engine.py             # Break of Structure
│   │   │   ├── choch_engine.py           # Change of Character
│   │   │   ├── trendline_engine.py       # Trendline computation
│   │   │   ├── zones_engine.py           # Supply/demand zones
│   │   │   ├── mtf_sr_engine.py          # Multi-timeframe S/R
│   │   │   ├── session_engine.py         # Trading session boxes
│   │   │   ├── narrative_engine.py       # Plain-English narrative
│   │   │   ├── framework_checker.py      # Trade framework checklist
│   │   │   ├── data_service.py           # OHLC data fetching
│   │   │   ├── mt5_store.py              # In-memory candle store
│   │   │   └── structure_cache.py        # Analysis result caching
│   │   └── mt5-bridge/
│   │       └── mt5_bridge.py             # Windows MT5 ↔ API bridge
│   │
│   └── trading-dashboard/                # React + Vite frontend
│       └── src/
│           ├── App.tsx                   # Router + global providers
│           ├── pages/
│           │   ├── Dashboard.tsx         # Main trading view
│           │   └── AnalysisPage.tsx      # Full narrative + framework view
│           ├── components/
│           │   ├── TradingChart.tsx      # Candlestick chart + all overlays
│           │   ├── TopBar.tsx            # Symbol/timeframe/trend controls
│           │   ├── TradePanel.tsx        # Order entry + position manager
│           │   ├── MarketNarrative.tsx   # Plain-English commentary panel
│           │   ├── FrameworkPanel.tsx    # SCALP/LIMIT step-by-step checker
│           │   ├── FrameworkMonitor.tsx  # Live active setup monitor
│           │   ├── HeatmapSidebar.tsx    # Currency heatmap
│           │   └── NewsPanel.tsx         # News impact status per pair
│           └── hooks/
│               ├── use-trading-api.ts    # All TanStack Query data hooks
│               └── use-framework-check.ts # Framework check polling hook
```

---

## Stopping the App

Close the three terminal windows:

- `STRUCT.ai - Trading API`
- `STRUCT.ai - Dashboard`
- `STRUCT.ai - MT5 Bridge`

Or press `Ctrl+C` in each terminal if you launched manually.

---

## Troubleshooting

**`MetaTrader5` package not found**
The MT5 Python package is Windows-only. This project requires a Windows machine with MT5 installed.

**Dashboard shows no data / spinner indefinitely**
Make sure MT5 is open and logged in, and that `mt5_bridge.py` is running. Check the API is healthy at `http://localhost:8001/docs`.

**Port already in use**
Close any previous STRUCT.ai terminal windows and retry.

**News panel shows "service unavailable"**
The news impact feature connects to a separate news service (Repo 3). Without it running, the panel degrades gracefully — trading is not blocked.

---

## Course Context

Built as a university AI course project to demonstrate applied use of:

- **Python** for backend API design and algorithmic data processing
- **numpy / pandas** for time-series financial data manipulation (swing detection, zone clustering, S/R scoring)
- **FastAPI** for modern async REST API and WebSocket design
- **React + TypeScript** for a real-time data-driven frontend
- **Full-stack system design** — bridging proprietary desktop software (MT5) to a web application via a custom HTTP/WebSocket pipeline

The analysis engines implement established rule-based market structure concepts (ICT / Smart Money Concepts) in clean, testable Python — no black-box ML, every decision traceable through the code.

---

## License

MIT
#   S t u r c t - a i . 2 . 0  
 