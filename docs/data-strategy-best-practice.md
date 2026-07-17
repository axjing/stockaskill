# Quant Data Cache-First + Incremental Sync: Best Practice Specification

## 1. Architecture Overview

```
                    +-----------------------------------------+
                    |           Application Layer              |
                    |  (scan, diagnose, alpha, backtest...)    |
                    +----------------+------------------------+
                                     | read(symbol, start, end)
                    +----------------v------------------------+
                    |          Data Engine (Orchestrator)       |
                    |                                          |
                    |  1. Check SQLite cache                   |
                    |  2. Compute missing gaps                 |
                    |  3. Fetch gaps via source chain          |
                    |  4. UPSERT into cache                    |
                    |  5. Return merged result                 |
                    +-+--------------+--------------+---------+
                      |              |              |
              +-------v------+ +-----v------+ +----v--------+
              |  Source A    | | Source B   | | Source C    |
              |  AKShare     | | baostock   | | efinance    |
              |  (primary)   | | (fallback) | | (fallback)  |
              +--------------+ +------------+ +-------------+
                      |              |              |
              +-------v--------------v--------------v--------+
              |            SQLite Cache Layer                 |
              |  quant_cache.db                               |
              |  +-----------+----------+------------------+  |
              |  | symbols   | ohlcv    | sync_watermarks  |  |
              |  | metadata  | daily    | (gap tracking)   |  |
              |  +-----------+----------+------------------+  |
              +------------------------------------------------+
```

## 2. SQLite Schema Design

```sql
-- Symbol metadata
CREATE TABLE IF NOT EXISTS symbols (
    symbol        TEXT NOT NULL,
    market        TEXT NOT NULL,
    name          TEXT,
    exchange      TEXT,
    currency      TEXT DEFAULT 'CNY',
    first_trading TEXT,
    last_trading  TEXT,
    is_active     INTEGER DEFAULT 1,
    updated_at    TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, market)
);

-- OHLCV daily data
CREATE TABLE IF NOT EXISTS ohlcv_daily (
    symbol        TEXT NOT NULL,
    market        TEXT NOT NULL,
    date          TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        REAL,
    amount        REAL,
    turn_over     REAL,
    source        TEXT DEFAULT 'unknown',
    fetched_at    TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, market, date)
);

-- Sync watermarks (critical for incremental strategy)
CREATE TABLE IF NOT EXISTS sync_watermarks (
    symbol        TEXT NOT NULL,
    market        TEXT NOT NULL,
    granularity   TEXT DEFAULT 'daily',
    last_date     TEXT,
    earliest_date TEXT,
    row_count     INTEGER DEFAULT 0,
    last_sync_at  TEXT DEFAULT (datetime('now')),
    sync_source   TEXT,
    sync_status   TEXT DEFAULT 'ok',
    error_msg     TEXT,
    PRIMARY KEY (symbol, market, granularity)
);

-- Source health tracking (circuit breaker support)
CREATE TABLE IF NOT EXISTS source_health (
    source        TEXT NOT NULL PRIMARY KEY,
    total_calls   INTEGER DEFAULT 0,
    failed_calls  INTEGER DEFAULT 0,
    last_error    TEXT,
    last_success  TEXT,
    backoff_until TEXT,
    is_healthy    INTEGER DEFAULT 1,
    updated_at    TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_date
    ON ohlcv_daily (symbol, market, date);
CREATE INDEX IF NOT EXISTS idx_ohlcv_date_range
    ON ohlcv_daily (date, symbol, market);
CREATE INDEX IF NOT EXISTS idx_watermark_lookup
    ON sync_watermarks (symbol, market, granularity);
```

## 3. Core Strategy: Cache-First + Incremental Sync

### 3.1 Read Path

```python
def get_ohlcv(symbol, market, start, end, granularity='daily'):
    # Step 1: Read from cache
    cached = db.query('''
        SELECT * FROM ohlcv_daily
        WHERE symbol = ? AND market = ?
          AND date >= ? AND date <= ?
        ORDER BY date
    ''', (symbol, market, start, end))

    # Step 2: Check if cache fully covers the range
    gap = compute_gap(cached, start, end)
    if not gap:
        return cached  # cache hit

    # Step 3: Fetch missing range via source chain
    fresh = fetch_with_fallback(symbol, market, gap.start, gap.end, granularity)

    # Step 4: UPSERT fresh data
    if fresh:
        upsert_ohlcv(fresh)
        update_watermark(symbol, market, fresh)

    # Step 5: Return merged result
    return merge(cached, fresh)
```

### 3.2 Gap Computation

```python
def compute_gap(cached_rows, requested_start, requested_end):
    if not cached_rows:
        return Gap(requested_start, requested_end)

    cached_dates = sorted(r['date'] for r in cached_rows)
    earliest, latest = cached_dates[0], cached_dates[-1]
    gaps = []

    if earliest > requested_start:
        gaps.append(Gap(requested_start, earliest))

    if latest < requested_end:
        overlap_start = max(latest, _shift_trading_days(latest, -3))
        gaps.append(Gap(overlap_start, requested_end))

    return merge_gaps(gaps) if gaps else None
```

### 3.3 Full History Seed

```python
def seed_full_history(symbol, market):
    baseline = {
        'A': '2000-01-01',
        'HK': '1995-01-01',
        'US': '1990-01-01',
        'ETF': '2004-01-01',
    }
    start = baseline.get(market, '2000-01-01')
    end = date.today().isoformat()
    return get_ohlcv(symbol, market, start, end)
```

## 4. Multi-Source Fallback Chain

### 4.1 Source Priority by Market

```
A-shares:  AKShare (EastMoney) -> baostock -> efinance
HK:        AKShare -> yfinance
US:        yfinance -> AKShare
ETF:       AKShare (fund_etf_hist_sina) -> efinance
```

### 4.2 Fallback with Circuit Breaker

```python
SOURCE_PRIORITY = {
    'A':   ['akshare', 'baostock', 'efinance'],
    'HK':  ['akshare', 'yfinance'],
    'US':  ['yfinance', 'akshare'],
    'ETF': ['akshare', 'efinance'],
}

def fetch_with_fallback(symbol, market, start, end, granularity='daily'):
    errors = []
    for source in SOURCE_PRIORITY.get(market, ['akshare']):
        if is_source_blocked(source):
            continue
        try:
            data = FETCHERS[source](symbol, market, start, end)
            if data and validate_ohlcv(data, start, end):
                record_source_success(source)
                return data
        except Exception as e:
            record_source_failure(source, str(e))
            errors.append(f'{source}: {e}')
    raise DataFetchError(f'All sources failed for {symbol}/{market}')
```

### 4.3 Circuit Breaker

```python
def record_source_failure(source, error_msg):
    db.execute('''
        UPDATE source_health
        SET failed_calls = failed_calls + 1,
            last_error = ?,
            is_healthy = CASE WHEN failed_calls > 5 THEN 0 ELSE 1 END,
            backoff_until = CASE
                WHEN failed_calls >= 10 THEN datetime('now', '+1 hour')
                WHEN failed_calls >= 5  THEN datetime('now', '+5 minutes')
                ELSE backoff_until
            END
        WHERE source = ?
    ''', (error_msg, source))

def record_source_success(source):
    db.execute('''
        UPDATE source_health
        SET failed_calls = 0, last_success = datetime('now'),
            is_healthy = 1, backoff_until = NULL
        WHERE source = ?
    ''', (source,))
```

## 5. UPSERT Logic

```python
def upsert_ohlcv(rows, source='unknown'):
    db.executemany('''
        INSERT INTO ohlcv_daily
            (symbol, market, date, open, high, low, close, volume, amount, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, market, date)
        DO UPDATE SET
            open = excluded.open, high = excluded.high,
            low = excluded.low, close = excluded.close,
            volume = excluded.volume, amount = excluded.amount,
            source = excluded.source,
            fetched_at = datetime('now')
    ''', [(r['symbol'], r['market'], r['date'],
             r.get('open'), r.get('high'), r.get('low'),
             r.get('close'), r.get('volume'), r.get('amount'), source)
            for r in rows])
    db.commit()
```

## 6. Data Validation

```python
def validate_ohlcv(data, start, end):
    if not data:
        return False
    required = {'date', 'open', 'high', 'low', 'close', 'volume'}
    if not required.issubset(data[0].keys()):
        return False
    for row in data:
        if any(row.get(c, 0) <= 0 for c in ('open', 'high', 'low', 'close')):
            return False
        if row['high'] < row['low']:
            return False
    dates = [r['date'] for r in data]
    if min(dates) < '2000-01-01' or max(dates) > date.today().isoformat():
        return False
    return True
```

## 7. Usage Patterns

### 7.1 Typical Read (Warm Cache)

```python
# Get 600519 daily data for last 90 days
end = date.today().isoformat()
start = (date.today() - timedelta(days=90)).isoformat()

# Internally:
# 1. Cache hit: 2020-01-01 to 2026-07-02
# 2. Gap: 2026-07-02 -> 2026-07-05 (3 days, with overlap)
# 3. Fetch gap only from AKShare
# 4. UPSERT 3 rows
# 5. Return 90 days (87 cached + 3 fresh)
data = engine.get_ohlcv('600519', 'A', start, end)
```

### 7.2 Cold Start

```python
# First run, no cache exists
# 1. Cache empty -> full range gap
# 2. Fetch 2000-01-01 to today
# 3. UPSERT ~6000 rows
# 4. Watermark recorded
data = engine.get_ohlcv('600519', 'A', '2000-01-01', end)
```

### 7.3 Batch Scan (200 Stocks)

```python
# Each symbol: check watermark -> compute small gap (0-5 days) -> fetch gap
# Total API calls ~= 200 x 1 = 200 (not 200 x 6000)
results = engine.batch_get_ohlcv(symbols, start, end)
```

## 8. Key Design Principles

| Principle | Rationale |
|---|---|
| Cache is the source of truth | API is a sync mechanism, not the query layer |
| Incremental by default | Never pull full history unless watermark is empty |
| Overlap on incremental fetch | Fetch `last_date - 3 days` to catch corrections |
| Latest data wins on UPSERT | Corrected data overwrites stale data |
| Source health matters | Circuit breaker prevents wasting rate limits |
| Validate before cache | Reject malformed data at ingestion |
| Watermark is metadata | Instant gap computation without scanning OHLCV |

## 9. Edge Cases

| Scenario | Handling |
|---|---|
| API returns empty range | Mark gap, do not retry aggressively |
| Date data changes (corporate action) | UPSERT overwrites; `fetched_at` tracks freshness |
| All sources fail | Return cached data with `stale` flag |
| Symbol delisted | `is_active = 0`; still serve historical data |
| Cache corrupted | Drop + reseed; watermark triggers cold start |
| System clock wrong | Validate dates 2000-01-01 to today |

## 10. Performance

| Operation | Latency | Notes |
|---|---|---|
| Cache read (90 days, 1 symbol) | < 5 ms | SQLite indexed |
| Cache read (90 days, 200 symbols) | < 50 ms | Batch SELECT |
| Incremental fetch (3 days, 1 symbol) | 200-800 ms | Single API call |
| Incremental fetch (3 days, 200 symbols) | 30-90 s | Rate-limited |
| Cold start (full history, 1 symbol) | 1-3 s | ~6000 rows |
| Cold start (full history, 200 symbols) | 5-15 min | With rate limit pauses |

## 11. Migration Path

1. **Add `sync_watermarks` table** -- instant gap detection
2. **Implement `compute_gap()`** -- replace full-history fetch
3. **Add source health tracking** -- circuit breaker
4. **Switch to `ak.stock_zh_a_hist()`** -- date-range API
5. **Add validation layer** -- reject malformed data
6. **Add batch read optimization** -- single query for multi-symbol
