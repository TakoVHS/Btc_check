import os, csv, time, sys, hashlib, shutil, datetime, logging
from decimal import Decimal
from typing import List, Tuple
import requests
from bitcoinlib.wallets import Wallet, wallet_delete
from mnemonic import Mnemonic

# ================== КОНФИГ ==================
INPUT_FILE   = "mnemonics.txt"
PROCESSED_DB = "processed.txt"

NETWORKS = ["bitcoin", "testnet"]    # ["bitcoin"] или ["testnet"]
PROFILES: List[Tuple[str,str,int]] = [
    ("bip44_legacy",  "legacy",      44),  # 1...
    ("bip49_p2sh",    "p2sh-segwit", 49),  # 3...
    ("bip84_segwit",  "segwit",      84),  # bc1q...
    ("bip86_taproot", "taproot",     86),  # bc1p...
]

N_ADDR      = 3        # адресов на профиль
BASE_SLEEP  = 0.8      # базовая пауза между запросами к API
MAX_RETRIES = 3        # ретраи для balancer API
TIMEOUT_S   = 12

KEEP_WALLETS = True    # False = удалять временные кошельки после выгрузки
ONLY_NONZERO = True    # делать отдельные CSV/summary только с ненулевыми
UPDATE_QUEUE = True    # очищать mnemonics.txt от успешно обработанных
MARK_INVALID_AS_PROCESSED = True  # убирать невалидные из очереди
# ============================================

def utc_stamp():
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%SZ")

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def api_url(net: str) -> str:
    return "https://blockstream.info/api/address/{}" if net == "bitcoin" \
           else "https://blockstream.info/testnet/api/address/{}"

def read_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f]
    except FileNotFoundError:
        return []

def write_lines(path: str, lines: List[str]):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + ("\n" if lines else ""))

def normalize_queue(lines: List[str]) -> List[str]:
    out, seen = [], set()
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):  # пропускаем пустые/комментарии
            continue
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def load_queue_and_processed():
    queue = normalize_queue(read_lines(INPUT_FILE))
    processed = set(normalize_queue(read_lines(PROCESSED_DB)))
    # фильтруем уже обработанные
    queue = [q for q in queue if q not in processed]
    return queue, processed

def addr_balance(url_tmpl: str, addr: str) -> Tuple[object,object,object]:
    # с ретраями и бэкоффом на 429/ошибки сети
    for attempt in range(1, MAX_RETRIES+1):
        try:
            r = requests.get(url_tmpl.format(addr), timeout=TIMEOUT_S)
            if r.status_code == 429:
                sleep = BASE_SLEEP * attempt * 2
                logging.warning("429 Too Many Requests, retry in %.1fs", sleep)
                time.sleep(sleep); continue
            r.raise_for_status()
            data = r.json()
            cs = data.get("chain_stats", {})
            ms = data.get("mempool_stats", {})
            confirmed   = cs.get("funded_txo_sum", 0) - cs.get("spent_txo_sum", 0)
            unconfirmed = ms.get("funded_txo_sum", 0) - ms.get("spent_txo_sum", 0)
            return confirmed, unconfirmed, confirmed + unconfirmed
        except Exception as e:
            if attempt == MAX_RETRIES:
                return f"ERR: {e}", "", ""
            sleep = BASE_SLEEP * attempt
            logging.warning("balance retry %d/%d in %.1fs: %s", attempt, MAX_RETRIES, sleep, e)
            time.sleep(sleep)
    return "ERR", "", ""

def summarize_rows(rows: List[List[object]]):
    # rows: [wallet_name, network, profile, index, addr, conf, unconf, total]
    totals = {}
    for r in rows:
        wname = r[0]
        total = r[7]
        if isinstance(total, int) or (isinstance(total, str) and total.isdigit()):
            totals[wname] = totals.get(wname, 0) + int(total)
    summary = []
    for wname, sats in totals.items():
        btc = Decimal(sats) / Decimal(10**8)
        summary.append([wname, sats, format(btc, "f")])
    return summary

def write_csv(path: str, header: List[str], rows: List[List[object]]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

def main():
    run_dir = os.path.join("runs", utc_stamp())
    ensure_dir(run_dir)

    # логгер в файл + консоль
    log_path = os.path.join(run_dir, "orchestrator.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
    )
    logging.info("Run dir: %s", run_dir)

    # подготовка очереди
    queue, processed = load_queue_and_processed()
    if not queue:
        logging.warning("В очереди нет фраз для обработки (после фильтра processed).")
    # бэкап входа
    if os.path.exists(INPUT_FILE):
        shutil.copy2(INPUT_FILE, os.path.join(run_dir, "mnemonics.txt.bak"))

    mnemo = Mnemonic("english")

    # накапливаем строки для CSV по сетям
    addr_header = ["wallet_name","network","profile","address_index","address",
                   "confirmed_sats","unconfirmed_sats","total_sats"]
    rows_by_net = {net: [] for net in NETWORKS}

    for idx, phrase in enumerate(queue, 1):
        is_valid = mnemo.check(phrase)
        if not is_valid:
            logging.warning("[%d] BAD MNEMONIC", idx)
            if MARK_INVALID_AS_PROCESSED:
                processed.add(phrase)
                write_lines(PROCESSED_DB, sorted(processed))
            continue

        # стабильное имя без утечки фразы — по хэшу
        short = hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8]

        for net in NETWORKS:
            url_tmpl = api_url(net)
            for prof_name, witness, purpose in PROFILES:
                wname = f"m_{short}_{prof_name}_{net}"

                # чистый старт
                try:
                    wallet_delete(wname, force=True)
                except Exception:
                    pass

                # создаём кошелёк из фразы
                try:
                    w = Wallet.create(
                        wname,
                        keys=phrase,
                        network=net,
                        witness_type=witness,
                        purpose=purpose,
                        account_id=0
                    )
                    logging.info("[%d] %s %s: Created %s", idx, net, prof_name, wname)
                except Exception as e:
                    logging.error("[%d] %s %s: CREATE ERROR: %s", idx, net, prof_name, e)
                    continue

                # адреса + баланс
                for i in range(N_ADDR):
                    k = w.new_key(change=0)
                    addr = k.address
                    conf, unconf, total = addr_balance(url_tmpl, addr)
                    logging.info("  [%d:%s:%s:%d] %s -> total=%s", idx, net, prof_name, i, addr, total)
                    rows_by_net[net].append([wname, net, prof_name, i, addr, conf, unconf, total])
                    time.sleep(BASE_SLEEP)

                # очистка кошелька при необходимости
                if not KEEP_WALLETS:
                    try:
                        wallet_delete(wname, force=True)
                    except Exception:
                        pass

        # фраза успешно обработана — добавим в processed и обновим файл
        processed.add(phrase)
        write_lines(PROCESSED_DB, sorted(processed))

    # запись CSV и сводок + только ненулевые
    for net, rows in rows_by_net.items():
        addr_csv = os.path.join(run_dir, f"mnemonics_addresses_{net}.csv")
        write_csv(addr_csv, addr_header, rows)
        summary = summarize_rows(rows)
        summary_csv = os.path.join(run_dir, f"mnemonics_summary_{net}.csv")
        write_csv(summary_csv, ["wallet_name","total_sats","total_btc"], summary)

        if ONLY_NONZERO:
            nz_rows = [r for r in rows if (isinstance(r[7], int) and r[7] > 0) or (isinstance(r[7], str) and r[7].isdigit() and int(r[7])>0)]
            nz_addr_csv = os.path.join(run_dir, f"mnemonics_addresses_{net}_nonzero.csv")
            write_csv(nz_addr_csv, addr_header, nz_rows)
            nz_summary = summarize_rows(nz_rows)
            nz_summary_csv = os.path.join(run_dir, f"mnemonics_summary_{net}_nonzero.csv")
            write_csv(nz_summary_csv, ["wallet_name","total_sats","total_btc"], nz_summary)

        # «последние» копии в корень проекта для удобства
        shutil.copy2(addr_csv,     f"mnemonics_addresses_{net}.csv")
        shutil.copy2(summary_csv,  f"mnemonics_summary_{net}.csv")
        if ONLY_NONZERO:
            shutil.copy2(nz_addr_csv,    f"mnemonics_addresses_{net}_nonzero.csv")
            shutil.copy2(nz_summary_csv, f"mnemonics_summary_{net}_nonzero.csv")

    # обновить очередь (убрать processed)
    if UPDATE_QUEUE and os.path.exists(INPUT_FILE):
        all_lines = normalize_queue(read_lines(INPUT_FILE))
        left = [s for s in all_lines if s not in processed]
        write_lines(INPUT_FILE, left)
        logging.info("Очередь обновлена: осталось %d строк(и)", len(left))

    logging.info("Готово. Результаты в %s", run_dir)

if __name__ == "__main__":
    main()
