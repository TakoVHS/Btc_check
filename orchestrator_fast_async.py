import os, csv, sys, time, hashlib, shutil, datetime, logging, asyncio, random
from decimal import Decimal
from typing import List, Tuple
import aiohttp
from bitcoinlib.wallets import Wallet, wallet_delete
from mnemonic import Mnemonic

# ===== КОНФИГ =====
INPUT_FILE   = "mnemonics.txt"
PROCESSED_DB = "processed.txt"

NETWORKS = ["bitcoin", "testnet"]     # можно ["bitcoin"] или ["testnet"]
PROFILES: List[Tuple[str,str,int]] = [
    ("bip44_legacy",  "legacy",      44),  # 1...
    ("bip49_p2sh",    "p2sh-segwit", 49),  # 3...
    ("bip84_segwit",  "segwit",      84),  # bc1q...
    ("bip86_taproot", "taproot",     86),  # bc1p...
]

N_ADDR        = 3        # адресов на профиль
KEEP_WALLETS  = True     # False = автоудалять временные кошельки (ещё быстрее)
ONLY_NONZERO  = True     # писать отдельные CSV с ненулевыми
UPDATE_QUEUE  = True     # чистить mnemonics.txt после прогона
MARK_INVALID_AS_PROCESSED = True

# Сеть/лимиты
TIMEOUT_S      = 12
MAX_RETRIES    = 3
MAX_CONC       = 12      # максимальная одновременная загрузка (10–16 — ок)
BASE_BACKOFF   = 0.5     # базовый бэкофф на ретраи (умножается)
# ==================

def utc_stamp(): return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%SZ")
def ensure_dir(p): os.makedirs(p, exist_ok=True)

def api_url(net: str) -> str:
    return "https://blockstream.info/api/address/{}" if net == "bitcoin" \
           else "https://blockstream.info/testnet/api/address/{}"

def read_lines(path: str):
    try:    return [ln.rstrip("\n") for ln in open(path, "r", encoding="utf-8")]
    except: return []

def write_lines(path: str, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + ("\n" if lines else ""))

def normalize_queue(lines):
    out, seen = [], set()
    for ln in lines:
        s = " ".join(ln.split())
        if not s or s.startswith("#"): continue
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def load_queue_and_processed():
    queue = normalize_queue(read_lines(INPUT_FILE))
    processed = set(normalize_queue(read_lines(PROCESSED_DB)))
    queue = [q for q in queue if q not in processed]
    return queue, processed

# --------- СБОР АДРЕСОВ (последовательно, быстро и надёжно) ---------
def collect_addresses(phrases: List[str], networks, profiles, n_addr, keep_wallets) -> List[List[object]]:
    """
    Возвращает список строк без баланса:
      [wname, net, prof_name, index, addr]
    """
    mnemo = Mnemonic("english")
    rows = []
    for idx, phrase in enumerate(phrases, 1):
        if not mnemo.check(phrase):
            logging.warning("[%d] BAD MNEMONIC", idx)
            continue
        short = hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8]

        for net in networks:
            for prof_name, witness, purpose in profiles:
                wname = f"m_{short}_{prof_name}_{net}"
                try:
                    wallet_delete(wname, force=True)
                except Exception:
                    pass
                try:
                    w = Wallet.create(
                        wname, keys=phrase, network=net,
                        witness_type=witness, purpose=purpose, account_id=0
                    )
                    logging.info("[%d] %s %s: Created %s", idx, net, prof_name, wname)
                except Exception as e:
                    logging.error("[%d] %s %s: CREATE ERROR: %s", idx, net, prof_name, e)
                    continue

                for i in range(n_addr):
                    k = w.new_key(change=0)
                    rows.append([wname, net, prof_name, i, k.address])

                if not keep_wallets:
                    try: wallet_delete(wname, force=True)
                    except Exception: pass
    return rows

# --------- АСИНХРОННАЯ ПРОВЕРКА БАЛАНСОВ ---------
async def fetch_one(session: aiohttp.ClientSession, url_tmpl: str, addr: str, sem: asyncio.Semaphore):
    # Всегда возвращаем числа (0 при ошибке)
    async with sem:
        backoff = BASE_BACKOFF
        for attempt in range(1, MAX_RETRIES+1):
            try:
                async with session.get(url_tmpl.format(addr), timeout=TIMEOUT_S) as r:
                    if r.status == 429:
                        await asyncio.sleep(backoff + random.random()*0.2)
                        backoff *= 2
                        continue
                    r.raise_for_status()
                    data = await r.json()
                    cs = data.get("chain_stats", {}) or {}
                    ms = data.get("mempool_stats", {}) or {}
                    conf = int(cs.get("funded_txo_sum", 0)) - int(cs.get("spent_txo_sum", 0))
                    uncf = int(ms.get("funded_txo_sum", 0)) - int(ms.get("spent_txo_sum", 0))
                    return conf, uncf, conf + uncf
            except Exception:
                if attempt == MAX_RETRIES:
                    return 0, 0, 0
                await asyncio.sleep(backoff + random.random()*0.2)
                backoff *= 2
        return 0, 0, 0

async def fetch_all_balances(rows_wo_bal: List[List[object]]):
    """
    rows_wo_bal: [wname, net, prof, idx, addr]
    return rows_with_bal: [wname, net, prof, idx, addr, conf, uncf, total]
    """
    sem = asyncio.Semaphore(MAX_CONC)
    out = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for wname, net, prof, idx, addr in rows_wo_bal:
            url_tmpl = api_url(net)
            tasks.append(fetch_one(session, url_tmpl, addr, sem))
        results = await asyncio.gather(*tasks)

    for (wname, net, prof, idx, addr), (conf, uncf, total) in zip(rows_wo_bal, results):
        out.append([wname, net, prof, idx, addr, conf, uncf, total])
    return out

def summarize_rows(rows):
    totals = {}
    for wname, net, prof, idx, addr, conf, uncf, tot in rows:
        if isinstance(tot, str): tot = int(tot) if tot.isdigit() else 0
        totals[wname] = totals.get(wname, 0) + int(tot)
    summary = []
    for wname, sats in totals.items():
        btc = Decimal(sats) / Decimal(10**8)
        summary.append([wname, sats, format(btc, "f")])
    return summary

def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def main():
    run_dir = os.path.join("runs", utc_stamp()); ensure_dir(run_dir)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(os.path.join(run_dir,"orchestrator.log"), encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)]
    )
    logging.info("Run dir: %s", run_dir)

    # Очередь
    queue, processed = load_queue_and_processed()
    if not queue:
        logging.warning("Очередь пуста после фильтра processed")

    # Бэкап входа
    if os.path.exists(INPUT_FILE):
        shutil.copy2(INPUT_FILE, os.path.join(run_dir, "mnemonics.txt.bak"))

    # 1) Сбор адресов
    addr_rows_wo_bal = collect_addresses(queue, NETWORKS, PROFILES, N_ADDR, KEEP_WALLETS)
    # 2) Асинхронное получение балансов
    addr_rows = asyncio.run(fetch_all_balances(addr_rows_wo_bal))

    # 3) Запись CSV/summary по сетям
    header = ["wallet_name","network","profile","address_index","address",
              "confirmed_sats","unconfirmed_sats","total_sats"]
    rows_by_net = {}
    for r in addr_rows:
        rows_by_net.setdefault(r[1], []).append(r)

    for net, rows in rows_by_net.items():
        addr_csv = os.path.join(run_dir, f"mnemonics_addresses_{net}.csv")
        write_csv(addr_csv, header, rows)
        summary = summarize_rows(rows)
        summary_csv = os.path.join(run_dir, f"mnemonics_summary_{net}.csv")
        write_csv(summary_csv, ["wallet_name","total_sats","total_btc"], summary)

        if ONLY_NONZERO:
            nz = [x for x in rows if int(x[7]) > 0]
            nz_addr = os.path.join(run_dir, f"mnemonics_addresses_{net}_nonzero.csv")
            write_csv(nz_addr, header, nz)
            nz_sum = summarize_rows(nz)
            nz_sum_csv = os.path.join(run_dir, f"mnemonics_summary_{net}_nonzero.csv")
            write_csv(nz_sum_csv, ["wallet_name","total_sats","total_btc"], nz_sum)

        # последние копии в корень
        shutil.copy2(addr_csv,    f"mnemonics_addresses_{net}.csv")
        shutil.copy2(summary_csv, f"mnemonics_summary_{net}.csv")
        if ONLY_NONZERO:
            shutil.copy2(nz_addr,    f"mnemonics_addresses_{net}_nonzero.csv")
            shutil.copy2(nz_sum_csv, f"mnemonics_summary_{net}_nonzero.csv")

    # 4) Обновляем processed/очередь
    if MARK_INVALID_AS_PROCESSED:
        # отметим и невалидные (они уже были пропущены на collect_addresses)
        mn = Mnemonic("english")
        for s in normalize_queue(read_lines(INPUT_FILE)):
            if not mn.check(s): processed.add(s)

    # добавим валидные, которые прошли сбор
    for s in queue:
        processed.add(s)
    write_lines(PROCESSED_DB, sorted(processed))

    if UPDATE_QUEUE and os.path.exists(INPUT_FILE):
        left = [s for s in normalize_queue(read_lines(INPUT_FILE)) if s not in processed]
        write_lines(INPUT_FILE, left)
        logging.info("Очередь обновлена: осталось %d", len(left))

    logging.info("Готово. Результаты в %s", run_dir)

if __name__ == "__main__":
    main()
