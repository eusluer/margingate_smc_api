#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio, aiohttp, socket, json, time
from aiohttp import ClientTimeout, TCPConnector
from typing import List, Dict, Tuple

# ---------- CONFIG ----------
TARGET_SIZE        = 50  # Test için küçültüldü
REQUIRED_INTERVALS = ["4h", "2h", "30m"]
MIN_BARS           = {"4h": 300, "2h": 300, "30m": 500}
OUTFILE            = "coins.json"

BINANCE_FAPI_HOSTS = ["fapi.binance.com","fapi1.binance.com","fapi2.binance.com","fapi3.binance.com"]
REQ_TIMEOUT        = 30
MAX_RETRY          = 2  
CONCURRENCY        = 10

# ---------- HTTP ----------
async def fetch_json(session: aiohttp.ClientSession, path: str, params: Dict | None = None):
    last_exc = None
    for attempt in range(MAX_RETRY):
        for host in BINANCE_FAPI_HOSTS:
            url = f"https://{host}{path}"
            try:
                async with session.get(url, params=params) as r:
                    r.raise_for_status()
                    return await r.json()
            except Exception as e:
                last_exc = e
                continue
        await asyncio.sleep(2 ** attempt)
    raise last_exc

# ---------- BUSINESS ----------
async def get_all_perp_sorted(session: aiohttp.ClientSession) -> List[str]:
    tickers = await fetch_json(session, "/fapi/v1/ticker/24hr")
    info    = await fetch_json(session, "/fapi/v1/exchangeInfo")
    perp_usdt = {s["symbol"] for s in info["symbols"]
                 if s["contractType"] == "PERPETUAL" and s["quoteAsset"] == "USDT"}
    rows = [(t["symbol"], float(t["quoteVolume"])) for t in tickers if t["symbol"] in perp_usdt]
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in rows]  # tüm liste, hacme göre sıralı

async def kline_ok(session: aiohttp.ClientSession, symbol: str, interval: str, min_bars: int) -> bool:
    try:
        kl = await fetch_json(session, "/fapi/v1/klines",
                              {"symbol": symbol, "interval": interval, "limit": min_bars})
        if not kl or len(kl) < min_bars:
            return False
        highs  = [float(x[2]) for x in kl]
        lows   = [float(x[3]) for x in kl]
        vols   = [float(x[5]) for x in kl]
        same_price_ratio = sum(1 for h, l in zip(highs, lows) if h == l) / len(kl)
        zero_vol_ratio   = sum(1 for v in vols if v == 0.0) / len(kl)
        return same_price_ratio <= 0.2 and zero_vol_ratio <= 0.2
    except Exception:
        return False

async def symbol_has_chart(session: aiohttp.ClientSession, symbol: str, sem: asyncio.Semaphore) -> bool:
    async with sem:
        for itv in REQUIRED_INTERVALS:
            if not await kline_ok(session, symbol, itv, MIN_BARS[itv]):
                return False
    return True

# ---------- MAIN ----------
async def main():
    timeout   = ClientTimeout(total=60, connect=15)
    connector = TCPConnector(ttl_dns_cache=600, family=socket.AF_INET, ssl=True, limit=100)
    sem       = asyncio.Semaphore(CONCURRENCY)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        all_syms = await get_all_perp_sorted(session)

        valid: List[str]   = []
        skipped: List[str] = []
        tasks: List[Tuple[str, asyncio.Task]] = []

        # Batch işlem - küçük gruplar halinde işle
        batch_size = 25
        processed = 0
        
        while len(valid) < TARGET_SIZE and processed < len(all_syms):
            # Batch oluştur
            current_batch = all_syms[processed:processed + batch_size]
            batch_tasks = []
            
            # Batch için task'ları oluştur
            for sym in current_batch:
                task = asyncio.create_task(symbol_has_chart(session, sym, sem))
                batch_tasks.append((sym, task))
            
            # Batch'i bekle
            for sym, task in batch_tasks:
                try:
                    ok = await asyncio.wait_for(task, timeout=45)
                    if ok:
                        valid.append(sym)
                        print(f"✅ {sym} eklendi ({len(valid)}/{TARGET_SIZE})")
                    else:
                        skipped.append(sym)
                        print(f"❌ {sym} atlandı (chart sorunu)")
                except asyncio.TimeoutError:
                    print(f"⏰ {sym} timeout")
                    skipped.append(sym)
                    task.cancel()
                except Exception as e:
                    print(f"❌ {sym} hata: {e}")
                    skipped.append(sym)
                
                # Hedefe ulaşıldıysa dur
                if len(valid) >= TARGET_SIZE:
                    # Kalan task'ları iptal et
                    for remaining_sym, remaining_task in batch_tasks:
                        if not remaining_task.done():
                            remaining_task.cancel()
                    break
            
            processed += batch_size
            
            # Batch'ler arası kısa mola
            if len(valid) < TARGET_SIZE and processed < len(all_syms):
                await asyncio.sleep(1)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "required_intervals": REQUIRED_INTERVALS,
        "min_bars": MIN_BARS,
        "symbols": valid[:TARGET_SIZE],
        "skipped": skipped
    }
    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"{len(valid[:TARGET_SIZE])} sembol yazıldı -> {OUTFILE}")
    print(f"Atılan (chart yok/bozuk) : {len(skipped)}")

if __name__ == "__main__":
    asyncio.run(main())