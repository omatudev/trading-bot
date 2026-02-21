# 🤖 AI Agent Context — Trading Bot

> Este documento contiene todo el contexto necesario para que un agente de IA pueda trabajar eficientemente en este proyecto. Léelo antes de hacer cualquier modificación.

---

## Índice

1. [Visión General](#1-visión-general)
2. [Stack Tecnológico](#2-stack-tecnológico)
3. [Estructura del Proyecto](#3-estructura-del-proyecto)
4. [Arquitectura y Flujo de Datos](#4-arquitectura-y-flujo-de-datos)
5. [Backend — Detalle de Módulos](#5-backend--detalle-de-módulos)
6. [Frontend — Detalle de Componentes](#6-frontend--detalle-de-componentes)
7. [Base de Datos](#7-base-de-datos)
8. [API Endpoints](#8-api-endpoints)
9. [WebSocket](#9-websocket)
10. [Scheduler — Trabajos Programados](#10-scheduler--trabajos-programados)
11. [Reglas de Trading](#11-reglas-de-trading)
12. [Patrones Críticos y Gotchas](#12-patrones-críticos-y-gotchas)
13. [Convenciones del Proyecto](#13-convenciones-del-proyecto)
14. [Errores Comunes y Cómo Evitarlos](#14-errores-comunes-y-cómo-evitarlos)
15. [Guía de Configuración](#15-guía-de-configuración)

---

## 1. Visión General

Sistema de **swing trading automatizado** para acciones del mercado estadounidense. Combina análisis con LLM (Gemini 2.5 Flash) para generar señales y un motor de reglas determinístico para ejecutar trades en Alpaca (paper trading).

**Frontend**: Dashboard minimalista a pantalla completa con un chart SVG como fondo animado, valores numéricos con transiciones animadas (NumberFlow), y paneles deslizantes.

**Backend**: API REST + WebSocket en FastAPI con scheduler que ejecuta análisis automáticos en horarios específicos del mercado.

---

## 2. Stack Tecnológico

### Backend

| Tecnología         | Versión | Propósito                                      |
| ------------------ | ------- | ---------------------------------------------- |
| Python             | 3.14    | Runtime                                        |
| FastAPI            | latest  | Framework web                                  |
| uvicorn            | latest  | Servidor ASGI                                  |
| alpaca-py          | latest  | API de trading (paper)                         |
| google-genai       | latest  | Gemini 2.5 Flash LLM                           |
| SQLAlchemy (async) | latest  | ORM con aiosqlite                              |
| APScheduler        | latest  | Tareas programadas                             |
| numpy              | latest  | Cálculos estadísticos para perfiles de tickers |
| pydantic-settings  | latest  | Configuración desde `.env`                     |

### Frontend

| Tecnología         | Versión | Propósito                                     |
| ------------------ | ------- | --------------------------------------------- |
| React              | 19.2    | UI framework                                  |
| TypeScript         | ~5.9.3  | Type safety                                   |
| Vite               | 7.3.1   | Build tool                                    |
| Tailwind CSS       | v4.2    | Estilos (via `@tailwindcss/vite` plugin)      |
| shadcn/ui          | latest  | Componentes base (Sheet, Switch, Input, etc.) |
| @number-flow/react | latest  | Transiciones numéricas animadas               |
| lucide-react       | latest  | Iconos                                        |
| sonner             | latest  | Toast notifications                           |

### Fuente tipográfica

- **Courier Prime** — definida como `--font-sans` en `index.css`, monoespaciada estilizada

---

## 3. Estructura del Proyecto

```
trading-bot/
├── backend/
│   ├── .env                    # API keys y configuración (NO commitear)
│   ├── .env.example            # Template de variables
│   ├── config.py               # Settings via pydantic-settings
│   ├── main.py                 # FastAPI app, endpoints, WebSocket, lifespan
│   ├── requirements.txt        # Dependencias Python
│   ├── core/
│   │   ├── alpaca_client.py    # Wrapper Alpaca Trading + Data APIs
│   │   ├── llm_analyst.py      # Motor Gemini 2.5 Flash
│   │   ├── rules_engine.py     # Reglas determinísticas de trading
│   │   └── scheduler.py        # Tareas programadas (APScheduler)
│   ├── database/
│   │   ├── models.py           # Modelos SQLAlchemy (5 tablas)
│   │   └── trading_bot.db      # Base de datos SQLite
│   └── modules/
│       ├── news_scanner.py     # Escaneo de noticias + análisis LLM
│       ├── position_manager.py # Gestión de posiciones y ejecución
│       └── ticker_profiler.py  # Perfiles de gap-up por ticker
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts          # Plugins: @vitejs/plugin-react, @tailwindcss/vite
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx             # Componente principal (fullscreen chart + overlay)
│       ├── config.ts           # URLs centralizadas (API_URL, WS_URL)
│       ├── index.css           # Tailwind v4 + Courier Prime + tema oscuro
│       ├── main.tsx            # Entry point
│       ├── types.ts            # Interfaces TypeScript
│       ├── components/
│       │   ├── BackgroundChart.tsx   # Chart SVG fullscreen con morphing
│       │   ├── ConfigSidebar.tsx     # Panel lateral de configuración
│       │   ├── PositionsTable.tsx    # Tabla de posiciones abiertas
│       │   ├── TradeHistory.tsx      # Historial de operaciones
│       │   ├── WatchlistPanel.tsx    # Lista de seguimiento
│       │   └── ui/                   # Componentes shadcn
│       ├── hooks/
│       │   └── useTradingBot.ts      # Hook WebSocket + REST helpers
│       └── lib/
│           └── utils.ts              # cn() helper
│
└── AGENT_CONTEXT.md            # Este documento
```

---

## 4. Arquitectura y Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCHEDULER (APScheduler)                  │
│  9:20am → Pre-market  │  9:30am → Open  │  10:00am → Mid-scan  │
│  3:30pm → Pre-close   │  Every 30s → Position rules check      │
│  9:30/12:00/4:00pm → Equity snapshots                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     NEWS SCANNER                             │
│  Alpaca News API (Benzinga) → últimas 3 días, 15 artículos  │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     LLM ANALYST (Gemini 2.5 Flash)           │
│  thinking_budget=0 │ response_mime_type="application/json"   │
│  Produce señales: BUY / SELL / HOLD con confidence 0-1       │
│  Retry con backoff en 429/RESOURCE_EXHAUSTED                 │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     RULES ENGINE (determinístico)            │
│  Valida señales antes de ejecutar. El LLM NUNCA override.    │
│  Take profit 10% │ 15 días en rojo │ Gap extraordinario      │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     POSITION MANAGER                         │
│  Orquesta ejecución: buy/sell/trailing stop via AlpacaClient │
│  Loguea trades │ Trackea fechas de apertura │ WebSocket push │
└────────────────────────────┬─────────────────────────────────┘
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
┌────────────────────────┐  ┌──────────────────────────────┐
│    ALPACA CLIENT        │  │    WEBSOCKET (broadcast)     │
│  Paper Trading API      │  │  → Frontend cada 5 segundos │
│  Async (to_thread)      │  │  portfolio_update            │
└────────────────────────┘  │  analysis_complete            │
                             │  trade_executed               │
                             └──────────┬───────────────────┘
                                        │
                                        ▼
                             ┌──────────────────────┐
                             │     FRONTEND          │
                             │  React + SVG Chart    │
                             │  NumberFlow anims     │
                             │  Paneles deslizantes  │
                             └──────────────────────┘
```

---

## 5. Backend — Detalle de Módulos

### 5.1 `config.py` — Configuración

Singleton `settings = Settings()` que lee desde `.env`:

| Variable                               | Default                                         | Descripción                              |
| -------------------------------------- | ----------------------------------------------- | ---------------------------------------- |
| `alpaca_api_key`                       | `""`                                            | API key de Alpaca                        |
| `alpaca_secret_key`                    | `""`                                            | Secret key de Alpaca                     |
| `alpaca_base_url`                      | `https://paper-api.alpaca.markets`              | Paper trading                            |
| `gemini_api_key`                       | `""`                                            | Google Gemini API key                    |
| `database_url`                         | `sqlite+aiosqlite:///./database/trading_bot.db` | BD async                                 |
| `take_profit_pct`                      | `10.0`                                          | % para auto-venta (take profit)          |
| `max_position_days_red`                | `15`                                            | Días máx en rojo antes de esperar salida |
| `min_profit_to_exit_red`               | `0.5`                                           | % mínimo para salir de zona roja         |
| `extraordinary_gap_sell_pct`           | `60.0`                                          | % a vender en gap extraordinario         |
| `ticker_profile_recalc_days`           | `30`                                            | Días entre recálculos de perfil          |
| `schedule_pre_open/open/mid/pre_close` | Específicos                                     | Horarios de ejecución (ET)               |

### 5.2 `alpaca_client.py` — Wrapper de Alpaca

**⚠️ PATRÓN CRÍTICO**: Todos los métodos del SDK de Alpaca son síncronos. Están envueltos en `await asyncio.to_thread(...)` para no bloquear el event loop de asyncio. **NUNCA** llamar métodos de `TradingClient` o `StockHistoricalDataClient` directamente sin `to_thread`.

Métodos principales:

- `get_portfolio_summary()` → equity, cash, buying_power, daily_pnl
- `get_open_positions()` → lista de posiciones con P&L
- `buy_market(ticker, qty)` / `sell_market(ticker, qty)`
- `sell_limit(ticker, qty, limit_price)` / `sell_trailing_stop(ticker, qty, trail_percent)`
- `get_historical_bars(ticker, timeframe, start, end)` → OHLCV bars
- `get_snapshot(ticker)` → trade, quote, daily bar, prev bar
- `is_market_open()` → bool (async)
- `get_market_clock()` → dict (async)

### 5.3 `llm_analyst.py` — Motor LLM

- Modelo: **Gemini 2.5 Flash** con `thinking_budget=0` (sin cadena de pensamiento)
- Respuestas en JSON (`response_mime_type="application/json"`)
- Retry: 3 intentos con backoff exponencial (5s base) en errores 429
- `analyze_ticker()` → señal BUY/SELL/HOLD con confidence, reasoning, catalysts
- `analyze_sell_override()` → puede overridear la regla de "nunca vender en rojo" solo con catalizador negativo confirmado

### 5.4 `rules_engine.py` — Reglas Determinísticas

**⚠️ REGLA FUNDAMENTAL**: El LLM NUNCA ejecuta trades ni overridea el rules engine. Solo produce señales.

| Regla                 | Descripción                                                                              |
| --------------------- | ---------------------------------------------------------------------------------------- |
| Take Profit           | Vender 100% si `unrealized_pnl_pct >= 10%`. Sin excepciones.                             |
| Gap Extraordinario    | Si gap > threshold del perfil: vender 60%, trailing stop 40% restante                    |
| Nunca vender en rojo  | No cerrar posición con pérdida, a menos que haya catalizador negativo confirmado por LLM |
| Zona roja (15 días)   | Si lleva >15 días en rojo → esperar +0.5% de ganancia para salir                         |
| Validación de entrada | Requiere catalizadores, confidence >= 0.5                                                |
| Tamaño de posición    | Máximo 20% del buying power                                                              |
| Momentum decay        | Detecta si los últimos 4 ticks muestran decaimiento (<30%)                               |

### 5.5 `position_manager.py` — Gestión de Posiciones

Orquesta la ejecución entre el análisis y Alpaca:

- `check_extraordinary_gaps()` → 9:30am: revisa gaps en cada posición
- `check_all_position_rules()` → cada 30s: take profit + gestión de pérdidas
- `execute_pending_signals()` → ejecuta señales pendientes del pre-market
- `evaluate_overnight_holds()` → 3:30pm: cierra posiciones sin señal positiva (nunca en rojo)
- Estado interno: `_pending_signals` y `_position_open_dates`
- Todos los trades se loguean en `trade_logs`

### 5.6 `news_scanner.py` — Escaneo de Noticias

- Usa `alpaca.data.historical.news.NewsClient` (Benzinga)
- Obtiene últimos 3 días, máximo 15 artículos por ticker
- Alimenta las noticias al LLM para análisis
- `scan_all_tickers()` → escanea todo el watchlist

### 5.7 `ticker_profiler.py` — Perfiles de Tickers

- Calcula threshold de "gap extraordinario" por ticker usando 4 meses de datos históricos
- Fórmula: `threshold = (avg_gap_up + max_gap_up + p75_gap_up) / 3`
- Se recalcula automáticamente cada 30 días
- Alerta si el threshold cambia >30% respecto al anterior

---

## 6. Frontend — Detalle de Componentes

### 6.1 `App.tsx` — Componente Principal

**Layout**: Pantalla completa con chart SVG como fondo + overlay con `pointer-events-none`.

```
div.relative.min-h-screen
  ├── BackgroundChart (absolute inset-0, llena todo el viewport)
  └── div.relative.z-10.pointer-events-none (overlay)
      ├── header (pointer-events-auto: título, búsqueda, ConfigSidebar)
      ├── main (valores centrales: NumberFlow para equity/price/P&L)
      ├── footer (pointer-events-auto: selector de períodos)
      └── paneles overlay (WatchlistPanel, PositionsTable, TradeHistory)
```

**Estado clave**:

- `searchTicker` / `searchInput` — búsqueda de ticker (Enter para activar)
- `tickerPrice` — precio actual del ticker buscado
- `chartChangePct` — % de cambio del chart actual
- `hoverPoint` — punto actual del mouse en el chart `{value, date}`
- `activePeriod` — período del chart ("1D", "1S", "1M", "3M", "6M", "1A", "all")
- `numericValue = hoverPoint?.value ?? baseValue` — hover overridea el display

**NumberFlow patterns**:

- Valor principal: `style: "decimal"`, suffix " USD" (texto más pequeño con opacidad)
- Porcentaje: `style: "percent"` — el valor debe dividirse entre 100 antes de pasarlo
- Keep component mounted (no unmount/remount) para que la animación funcione

### 6.2 `BackgroundChart.tsx` — Chart SVG con Morphing

**⚠️ COMPONENTE COMPLEJO** — Chart SVG puro (sin librerías externas).

**Constantes**:

- `W=1000, H=400` — viewBox del SVG
- `PAD_Y=0.15` — padding vertical
- `SAMPLES=200` — puntos fijos para morphing
- `ANIM_MS=600` — duración de animación

**Mecanismo de morphing**:

1. `resample(arr, n)` — interpola linealmente cualquier array a exactamente `n` puntos
2. Cuando llegan datos nuevos, `animateTo(targetYs)` interpola desde `currentYsRef` hasta el target
3. Usa `requestAnimationFrame` con ease-out cúbico: `t = 1 - (1-t)^3`
4. `buildPaths(ys)` genera strings SVG para línea + área de relleno
5. Gradiente verde (up) o rojo (down)

**Timeframes dinámicos según período**:
| Período | Days param | Timeframe |
|---|---|---|
| 1D | 2 | 5min |
| 1S (1 semana) | 8 | 15min |
| 1M | 35 | hour |
| 3M | 95 | day |
| 6M | 185 | day |
| 1A | 370 | day |
| all | 1825 | day |

**Hover**: Convierte coordenada X del mouse → índice de dato → emite `{value, date}` al padre. Línea vertical de crosshair en la posición.

**⚠️ GOTCHA**: Para portfolio history (sin ticker), deduplica por día para evitar puntos repetidos de las 3 snapshots diarias.

### 6.3 `ConfigSidebar.tsx`

Sheet (shadcn) que se desliza desde la derecha:

- Portfolio stats (Cash, Invertido, Buying Power)
- 3 switches para paneles (Posiciones, Historial, Watchlist)
- Horarios editables (Pre-apertura, Apertura, Mid-morning, Pre-cierre)
- Reglas editables (Take profit %, Gap-up %, Días máx rojo, Salida mín %)
- **Auto-save**: debounce de 800ms al editar, PUT a `/api/settings`

### 6.4 `useTradingBot.ts` — Hook WebSocket

- Conexión WebSocket a `WS_URL` con auto-reconnect (3s delay)
- Maneja: `portfolio_update`, `analysis_complete`, `trade_executed`
- Toasts en español para trades y análisis completado
- Helpers REST: `fetchPortfolio()`, `fetchSignals()`, `fetchWatchlist()`, `addTicker()`, `removeTicker()`, `triggerAnalysis()`

### 6.5 `config.ts` — URLs Centralizadas

```typescript
export const API_URL = "http://localhost:8000/api";
export const WS_URL = "ws://localhost:8000/ws";
```

**⚠️ IMPORTANTE**: Todos los fetch/WebSocket del frontend DEBEN usar estas constantes. No hardcodear URLs.

---

## 7. Base de Datos

SQLAlchemy async + aiosqlite. Archivo: `backend/database/trading_bot.db`

### Tablas

#### `ticker_profiles`

| Columna                       | Tipo       | Descripción                  |
| ----------------------------- | ---------- | ---------------------------- |
| `ticker` (PK)                 | String(10) | Símbolo del ticker           |
| `analysis_date`               | DateTime   | Fecha de análisis            |
| `analysis_period_months`      | Integer    | Meses analizados (default 4) |
| `days_analyzed`               | Integer    | Total de días en el período  |
| `days_gap_up`                 | Integer    | Días con gap-up              |
| `gap_up_frequency_pct`        | Float      | Frecuencia de gap-ups (%)    |
| `gap_up_avg_pct`              | Float      | Gap-up promedio (%)          |
| `gap_up_max_pct`              | Float      | Gap-up máximo (%)            |
| `gap_up_p75_pct`              | Float      | Percentil 75 de gap-ups      |
| `threshold_extraordinary_pct` | Float      | Threshold calculado          |
| `next_recalc_date`            | DateTime   | Próxima fecha de recálculo   |

#### `signals`

| Columna           | Tipo           | Descripción             |
| ----------------- | -------------- | ----------------------- |
| `id` (PK)         | Integer (auto) | ID                      |
| `ticker`          | String(10)     | Ticker analizado        |
| `signal`          | String(10)     | BUY / SELL / HOLD       |
| `confidence`      | Float          | 0.0 a 1.0               |
| `reasoning`       | Text           | Razonamiento del LLM    |
| `catalysts`       | Text (JSON)    | Lista de catalizadores  |
| `catalyst_type`   | String(50)     | Tipo de catalizador     |
| `sentiment_score` | Float          | Sentimiento             |
| `risk_level`      | String(20)     | Nivel de riesgo         |
| `analysis_window` | String(20)     | Ventana de análisis     |
| `raw_response`    | Text           | Respuesta cruda del LLM |

#### `trade_logs`

| Columna     | Tipo           | Descripción                             |
| ----------- | -------------- | --------------------------------------- |
| `id` (PK)   | Integer (auto) | ID                                      |
| `ticker`    | String(10)     | Ticker                                  |
| `action`    | String(30)     | BUY/SELL/TAKE_PROFIT/EXIT_RED_ZONE/etc. |
| `side`      | String(10)     | buy/sell                                |
| `qty`       | Float          | Cantidad                                |
| `price`     | Float          | Precio                                  |
| `pnl_pct`   | Float          | P&L porcentual                          |
| `pnl_usd`   | Float          | P&L en dólares                          |
| `order_id`  | String(50)     | ID de orden Alpaca                      |
| `reason`    | Text           | Motivo                                  |
| `signal_id` | Integer        | FK a signals.id                         |

#### `position_tracker`

| Columna        | Tipo       | Descripción       |
| -------------- | ---------- | ----------------- |
| `ticker` (PK)  | String(10) | Ticker            |
| `opened_at`    | DateTime   | Fecha de apertura |
| `opened_price` | Float      | Precio de entrada |
| `opened_qty`   | Float      | Cantidad comprada |
| `signal_id`    | Integer    | FK a signals.id   |
| `notes`        | Text       | Notas             |

#### `equity_snapshots`

| Columna               | Tipo           | Descripción     |
| --------------------- | -------------- | --------------- |
| `id` (PK)             | Integer (auto) | ID              |
| `timestamp` (indexed) | DateTime       | Timestamp       |
| `equity`              | Float          | Equity total    |
| `cash`                | Float          | Cash disponible |
| `invested`            | Float          | Monto invertido |

---

## 8. API Endpoints

Base URL: `http://localhost:8000`

| Método   | Path                      | Descripción                                                                        |
| -------- | ------------------------- | ---------------------------------------------------------------------------------- |
| `GET`    | `/api/health`             | Health check                                                                       |
| `GET`    | `/api/portfolio`          | Resumen de portfolio + posiciones abiertas                                         |
| `GET`    | `/api/watchlist`          | Todos los perfiles de tickers                                                      |
| `POST`   | `/api/watchlist/{ticker}` | Agregar ticker al watchlist (ejecuta análisis de perfil)                           |
| `DELETE` | `/api/watchlist/{ticker}` | Eliminar ticker del watchlist                                                      |
| `GET`    | `/api/signals`            | Últimas 20 señales LLM                                                             |
| `GET`    | `/api/settings`           | Configuración actual (reglas + horarios)                                           |
| `PUT`    | `/api/settings`           | Actualizar configuración (persiste en `.env`)                                      |
| `POST`   | `/api/analyze/{ticker}`   | Análisis manual LLM para un ticker                                                 |
| `GET`    | `/api/bars/{ticker}`      | Bars OHLCV. Query params: `days` (int), `tf` (min/5min/15min/hour/day)             |
| `GET`    | `/api/portfolio/history`  | Historial de equity desde snapshots. Query param: `period` (1D/1W/1M/3M/6M/1A/all) |
| `GET`    | `/api/trades`             | Últimos 50 trade logs                                                              |
| `WS`     | `/ws`                     | WebSocket para actualizaciones en tiempo real                                      |

---

## 9. WebSocket

**URL**: `ws://localhost:8000/ws`

### Tipos de mensaje (server → client)

```json
// portfolio_update (cada 5 segundos)
{
  "type": "portfolio_update",
  "portfolio": { "equity": 4000.0, "cash": 2000.0, ... },
  "positions": [...],
  "timestamp": "2025-01-01T12:00:00"
}

// analysis_complete (después de scan)
{
  "type": "analysis_complete",
  "signals": [...],
  "timestamp": "..."
}

// trade_executed (después de un trade)
{
  "type": "trade_executed",
  "trade": { "ticker": "AAPL", "action": "BUY", "qty": 5, ... },
  "timestamp": "..."
}
```

### Comportamiento del frontend

- Auto-reconnect con 3 segundos de delay
- Actualiza `portfolio`, `positions`, `signals` en el estado del dashboard
- Muestra toasts (sonner) para trades y análisis completados
- Labels en español: BUY→Compra, SELL→Venta, TAKE_PROFIT→Take Profit, etc.

---

## 10. Scheduler — Trabajos Programados

Timezone: **US/Eastern**

| Job ID                  | Horario     | Descripción                                                    |
| ----------------------- | ----------- | -------------------------------------------------------------- |
| `pre_market`            | 9:20am L-V  | Escanea todos los tickers, genera señales, almacena pendientes |
| `market_open`           | 9:30am L-V  | Revisa gaps extraordinarios + ejecuta señales pendientes       |
| `mid_morning`           | 10:00am L-V | Segundo escaneo, ejecuta señales BUY                           |
| `pre_close`             | 3:30pm L-V  | Análisis final, decide holds overnight vs cierres              |
| `profile_recalc`        | 8:00am L-V  | Recalcula perfiles expirados (cada 30 días)                    |
| `position_rules`        | Cada 30 seg | Revisa take profit / reglas de pérdida en posiciones abiertas  |
| `equity_snapshot_open`  | 9:30am L-V  | Guarda snapshot de equity                                      |
| `equity_snapshot_mid`   | 12:00pm L-V | Guarda snapshot de equity                                      |
| `equity_snapshot_close` | 4:00pm L-V  | Guarda snapshot de equity                                      |

---

## 11. Reglas de Trading

### Reglas irrompibles (NUNCA modificar sin consentimiento)

1. **El LLM solo produce señales** — nunca ejecuta trades directamente
2. **Take profit automático al 10%** — sin excepciones, se ejecuta inmediatamente
3. **Nunca vender en rojo** — solo si hay catalizador negativo confirmado por LLM
4. **Zona roja de 15 días** — después de 15 días en rojo, esperar +0.5% para salir
5. **Gap extraordinario** — vender 60%, trailing stop en el 40% restante
6. **Tamaño máximo de posición** — 20% del buying power
7. **Catalizadores obligatorios** — no se compra sin catalizadores identificados
8. **Confidence mínima 0.5** — para entrada y para hold overnight

### Fórmula de gap extraordinario

```
threshold = (avg_gap_up + max_gap_up + p75_gap_up) / 3
```

Basado en 4 meses de datos históricos por ticker.

---

## 12. Patrones Críticos y Gotchas

### Backend

#### ⚠️ Alpaca SDK es síncrono

```python
# ❌ INCORRECTO — bloquea el event loop
account = self.trading_client.get_account()

# ✅ CORRECTO — ejecuta en thread separado
account = await asyncio.to_thread(self.trading_client.get_account)
```

**Todos** los métodos de `TradingClient` y `StockHistoricalDataClient` DEBEN envolverse en `asyncio.to_thread()`.

#### ⚠️ Datos vacíos en fines de semana

Si pides `days=1` un sábado o domingo, Alpaca devuelve datos vacíos. Usa `days=2` mínimo para el período "1D" (el frontend usa `days=2` por eso).

#### ⚠️ Rate limits de Gemini

El LLM tiene retry con backoff exponencial (3 intentos, 5s base) para errores 429/RESOURCE_EXHAUSTED. No agregar llamadas al LLM sin considerar rate limits.

#### ⚠️ Persistencia de settings

`PUT /api/settings` escribe directamente al archivo `.env` usando `_persist_env()`. Si el formato del `.env` cambia, esta función podría romper.

#### ⚠️ Instancias singleton

`main.py` crea instancias singleton de todos los servicios a nivel de módulo. NO crear instancias adicionales — reutilizar las existentes.

### Frontend

#### ⚠️ pointer-events pattern

El overlay es `pointer-events-none` para que el chart SVG de fondo reciba eventos del mouse (hover/crosshair). Los elementos interactivos dentro del overlay DEBEN tener `pointer-events-auto`.

```jsx
// ❌ INCORRECTO — el botón no recibirá clicks
<div className="pointer-events-none">
  <button>Click me</button>
</div>

// ✅ CORRECTO
<div className="pointer-events-none">
  <button className="pointer-events-auto">Click me</button>
</div>
```

#### ⚠️ NumberFlow — no desmontar

Para que las animaciones funcionen, el componente `NumberFlow` debe permanecer montado. Cambiar el `value` prop triggers la animación. Si desmontás y remontás, no hay animación.

#### ⚠️ NumberFlow — porcentajes

`style: "percent"` multiplica el valor por 100 automáticamente. Si tu valor ya es un porcentaje (ej: `17.3`), dividilo entre 100 antes de pasarlo:

```jsx
<NumberFlow value={pct / 100} format={{ style: "percent" }} />
```

#### ⚠️ Chart morphing — 200 puntos fijos

El chart siempre resamplea a exactamente 200 puntos. Esto permite morphing suave entre datasets de distinto tamaño. No cambiar `SAMPLES` sin ajustar la animación.

#### ⚠️ URLs centralizadas

Todas las URLs de API/WebSocket deben importarse desde `config.ts`. No hardcodear `http://localhost:8000`.

#### ⚠️ Tailwind CSS v4

Este proyecto usa Tailwind CSS v4 (no v3). La sintaxis de configuración es diferente:

- Se importa con `@import "tailwindcss"` en CSS
- Plugin via `@tailwindcss/vite` (no PostCSS)
- Las variables de tema se definen con `@theme` en CSS

---

## 13. Convenciones del Proyecto

### Idioma

- **UI**: Español (Compra, Venta, Posiciones abiertas, Historial de operaciones, etc.)
- **Código**: Inglés (nombres de variables, funciones, clases)
- **Toasts**: Español
- **Fechas**: Formato `es-MX` en el frontend

### Estilo visual

- **Minimalismo extremo** — fondo oscuro con radial gradient, chart ocupa todo el viewport
- **Color**: Verde para ganancias (`rgba(34,197,94,...)`), rojo para pérdidas (`rgba(239,68,68,...)`)
- **Fuente**: Courier Prime (monoespaciada estilizada)
- **Tema**: Solo modo oscuro, oklch color system
- **Paneles**: Se deslizan desde abajo con gradiente `bg-gradient-to-t from-background/95`
- **Sidebar**: Se desliza desde la derecha (Sheet de shadcn)

### Acciones de trade (labels)

| Acción interna           | Label en español             |
| ------------------------ | ---------------------------- |
| `BUY`                    | Compra                       |
| `SELL`                   | Venta                        |
| `TAKE_PROFIT`            | Take Profit                  |
| `EXIT_RED_ZONE`          | Salida Zona Roja             |
| `CLOSE_EOD`              | Cierre fin de día            |
| `EXTRAORDINARY_GAP_SELL` | Venta por Gap Extraordinario |

### Colores de badges por acción

| Acción                 | Color     |
| ---------------------- | --------- |
| BUY                    | Verde     |
| SELL                   | Rojo      |
| TAKE_PROFIT            | Esmeralda |
| EXIT_RED_ZONE          | Naranja   |
| CLOSE_EOD              | Amarillo  |
| EXTRAORDINARY_GAP_SELL | Púrpura   |

---

## 14. Errores Comunes y Cómo Evitarlos

| Error                              | Causa                              | Solución                                                                      |
| ---------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------- |
| Chart plano/sin datos              | Fin de semana, `days=1`            | Usar `days=2` mínimo                                                          |
| NumberFlow no anima                | Se desmontó/remontó el componente  | Mantener montado, solo cambiar `value`                                        |
| Porcentaje muestra 1730%           | `style: "percent"` multiplica ×100 | Dividir entre 100 antes de pasar                                              |
| Hover no funciona en chart         | Overlay bloquea eventos            | Overlay: `pointer-events-none`, elementos interactivos: `pointer-events-auto` |
| Event loop se congela              | Llamada síncrona de Alpaca SDK     | Envolver en `asyncio.to_thread()`                                             |
| Error 429 de Gemini                | Rate limit excedido                | Ya hay retry con backoff, no agregar llamadas innecesarias                    |
| Settings no persisten              | Fallo al escribir `.env`           | Verificar que `_persist_env()` maneje el formato correctamente                |
| WebSocket no reconecta             | Servidor reiniciado                | Ya hay auto-reconnect a 3s, verificar que el servidor esté arriba             |
| Chart no muestra portfolio history | Puntos duplicados de 3 snapshots   | Deduplicar por día (ya implementado en `BackgroundChart`)                     |
| Import error en frontend           | URL hardcodeada                    | Importar `API_URL`/`WS_URL` desde `config.ts`                                 |

---

## 15. Guía de Configuración

### Iniciar el proyecto

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env  # Configurar API keys
python -m uvicorn main:app --reload --port 8000

# Frontend
cd frontend
bun install  # o npm install
bun dev      # localhost:5173
```

### Variables de entorno requeridas (`.env`)

```env
ALPACA_API_KEY=tu_key_aqui
ALPACA_SECRET_KEY=tu_secret_aqui
ALPACA_BASE_URL=https://paper-api.alpaca.markets
GEMINI_API_KEY=tu_gemini_key_aqui
DATABASE_URL=sqlite+aiosqlite:///./database/trading_bot.db
```

### Ports

- **Backend**: `http://localhost:8000`
- **Frontend**: `http://localhost:5173`
- **WebSocket**: `ws://localhost:8000/ws`

---

> **Última actualización**: Junio 2025
> **Generado por**: Auditoría completa del codebase (frontend + backend)
