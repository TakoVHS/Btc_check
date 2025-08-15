import os, csv, sys, asyncio, random, logging, shutil
from decimal import Decimal
from typing import Dict, Tuple, List
from datetime import datetime, UTC
import aiohttp

INPUT_CSV     = "derived_addresses_only.csv"
ONLY_NONZERO  = int(os.getenv("ONLY_NONZERO","1"))==1
TIMEOUT_S     = 12
MAX_RETRIES   = 3
MAX_CONC      = int(os.getenv("MAX_CONC","48"))
BASE_BACKOFF  = float(os.getenv("BASE_BACKOFF","0.3"))

def utc_stamp(): return datetime.now(UTC).strftime("%Y%m%d_%H%M%SZ")
def api_url(net: str) -> str:
    return "https://blockstream.info/api/address/{}" if net=="bitcoin" else "https://blockstream.info/testnet/api/address/{}"
def ensure_dir(p: str): os.makedirs(p, exist_ok=True)

def read_rows(path: str) -> List[dict]:
    if not os.path.exists(path): print(f"[ERR] Нет {path}"); sys.exit(1)
    with open(path,"r",encoding="utf-8") as f: return list(csv.DictReader(f))

async def fetch_one(session, url_tmpl: str, addr: str) -> Tuple[int,int,int]:
    backoff = BASE_BACKOFF
    for attempt in range(1, MAX_RETRIES+1):
        try:
            async with session.get(url_tmpl.format(addr), timeout=TIMEOUT_S) as resp:
                if resp.status == 429:
                    await asyncio.sleep(backoff + random.random()*0.2); backoff*=2; continue
                resp.raise_for_status()
                data = await resp.json()
                cs = data.get("chain_stats", {}) or {}
                ms = data.get("mempool_stats", {}) or {}
                conf = int(cs.get("funded_txo_sum",0)) - int(cs.get("spent_txo_sum",0))
                uncf = int(ms.get("funded_txo_sum",0)) - int(ms.get("spent_txo_sum",0))
                return conf, uncf, conf+uncf
        except Exception:
            if attempt==MAX_RETRIES: return 0,0,0
            await asyncio.sleep(backoff + random.random()*0.2); backoff*=2
    return 0,0,0

async def fetch_all(unique_by_net: Dict[str, List[str]]):
    out: Dict[tuple,Tuple[int,int,int]] = {}
    sem = asyncio.Semaphore(MAX_CONC)
    async with aiohttp.ClientSession() as session:
        tasks=[]
        for net,addrs in unique_by_net.items():
            url_tmpl = api_url(net)
            for a in addrs:
                async def task(net=net, addr=a, url=url_tmpl):
                    async with sem: return (net, addr, await fetch_one(session, url, addr))
                tasks.append(task())
        for net,addr,triple in await asyncio.gather(*tasks):
            out[(net,addr)] = triple
    return out

def summarize(rows: List[List[object]]):
    totals={}
    for wname,net,prof,idx,addr,conf,uncf,tot in rows:
        totals[wname]=totals.get(wname,0)+int(tot)
    return [[wid, sats, format(Decimal(sats)/Decimal(10**8), "f")] for wid,sats in totals.items()]

def write_csv(path: str, header, rows):
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(header); w.writerows(rows)

def main():
    run_dir = os.path.join("runs", utc_stamp()); ensure_dir(run_dir)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(run_dir,"check_balances.log"), encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    base_rows = read_rows(INPUT_CSV)
    unique_by_net={}
    for r in base_rows:
        net=r["network"].strip().lower(); addr=r["address"].strip()
        if not addr: continue
        unique_by_net.setdefault(net,[])
        if addr not in unique_by_net[net]: unique_by_net[net].append(addr)
    logging.info("Уникальных адресов: bitcoin=%d, testnet=%d",
                 len(unique_by_net.get("bitcoin",[])), len(unique_by_net.get("testnet",[])))
    balances = asyncio.run(fetch_all(unique_by_net))

    header=["wallet_id","network","profile","address_index","address","confirmed_sats","unconfirmed_sats","total_sats"]
    rows_by_net={}
    for r in base_rows:
        wname=r["wallet_id"]; net=r["network"].strip().lower()
        prof=r["profile"]; idx=r["address_index"]; addr=r["address"].strip()
        conf,uncf,tot = balances.get((net,addr),(0,0,0))
        rows_by_net.setdefault(net,[]).append([wname,net,prof,idx,addr,conf,uncf,tot])

    for net,rows in rows_by_net.items():
        addr_csv=os.path.join(run_dir,f"addresses_with_balance_{net}.csv"); write_csv(addr_csv, header, rows)
        sum_csv=os.path.join(run_dir,f"summary_{net}.csv"); write_csv(sum_csv, ["wallet_id","total_sats","total_btc"], summarize(rows))
        if ONLY_NONZERO:
            nz=[x for x in rows if int(x[7])>0]
            write_csv(os.path.join(run_dir,f"addresses_with_balance_{net}_nonzero.csv"), header, nz)
            write_csv(os.path.join(run_dir,f"summary_{net}_nonzero.csv"), ["wallet_id","total_sats","total_btc"], summarize(nz))
        # копии в корень для быстрого просмотра
        import shutil
        shutil.copy2(addr_csv, f"addresses_with_balance_{net}.csv")
        shutil.copy2(sum_csv,  f"summary_{net}.csv")
        if ONLY_NONZERO:
            shutil.copy2(os.path.join(run_dir,f"addresses_with_balance_{net}_nonzero.csv"), f"addresses_with_balance_{net}_nonzero.csv")
            shutil.copy2(os.path.join(run_dir,f"summary_{net}_nonzero.csv"),             f"summary_{net}_nonzero.csv")
    logging.info("Готово. Результаты в %s", run_dir)

if __name__=="__main__":
    main()
