import csv, time, requests, sys
from decimal import Decimal
from bitcoinlib.wallets import Wallet, wallet_delete
from mnemonic import Mnemonic

# --- настройки --- #
INPUT_FILE   = "mnemonics.txt"
NETWORKS     = ["bitcoin", "testnet"]   # можно оставить только одну: ["bitcoin"] или ["testnet"]
PROFILES     = [                         # (метка, witness_type, purpose)
    ("bip44_legacy",  "legacy",      44),
    ("bip49_p2sh",    "p2sh-segwit", 49),
    ("bip84_segwit",  "segwit",      84),
    ("bip86_taproot", "taproot",     86),
]
N_ADDR       = 3          # сколько receive-адресов на профиль
SLEEP        = 0.8        # задержка между запросами к API, чтобы не словить rate limit
KEEP_WALLETS = True       # False = удалять созданные кошельки после выгрузки адресов
# ------------------ #

def api_url(net: str) -> str:
    return "https://blockstream.info/api/address/{}" if net == "bitcoin" \
           else "https://blockstream.info/testnet/api/address/{}"

def addr_balance(url_tmpl: str, addr: str):
    try:
        r = requests.get(url_tmpl.format(addr), timeout=12)
        r.raise_for_status()
        data = r.json()
        cs, ms = data.get("chain_stats", {}), data.get("mempool_stats", {})
        confirmed   = cs.get("funded_txo_sum", 0) - cs.get("spent_txo_sum", 0)
        unconfirmed = ms.get("funded_txo_sum", 0) - ms.get("spent_txo_sum", 0)
        return confirmed, unconfirmed, confirmed + unconfirmed
    except Exception as e:
        return f"ERR: {e}", "", ""

def load_phrases(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except FileNotFoundError:
        print(f"[ERR] Нет файла {path}."); sys.exit(1)

def write_csv(path: str, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def summarize_to_csv(addresses_csv: str, summary_csv: str):
    # суммируем total_sats по wallet_name
    totals = {}  # wallet -> sats
    with open(addresses_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            wname = row["wallet_name"]
            total = row.get("total_sats", "")
            if total and str(total).isdigit():
                totals[wname] = totals.get(wname, 0) + int(total)
    rows = []
    for wname, sats in totals.items():
        btc = Decimal(sats) / Decimal(10**8)
        rows.append([wname, sats, format(btc, "f")])
    write_csv(summary_csv, ["wallet_name","total_sats","total_btc"], rows)

def process_network(net: str, phrases):
    print(f"\n=== NETWORK: {net} ===")
    url_tmpl = api_url(net)
    mnemo = Mnemonic("english")

    addr_rows = []  # строки для addresses CSV
    # CSV по адресам (с сетью и профилем)
    addr_header = ["wallet_name","network","profile","address_index","address",
                   "confirmed_sats","unconfirmed_sats","total_sats"]

    for idx, phrase in enumerate(phrases, 1):
        if not mnemo.check(phrase):
            print(f"[{idx}] BAD MNEMONIC"); continue

        for prof_name, witness, purpose in PROFILES:
            wname = f"mnemonic_{idx}_{prof_name}_{net}"

            # чистый старт
            try: wallet_delete(wname, force=True)
            except Exception: pass

            # создаём кошелёк по фразе
            try:
                w = Wallet.create(
                    wname,
                    keys=phrase,
                    network=net,
                    witness_type=witness,
                    purpose=purpose,
                    account_id=0
                )
                print(f"[{idx}] {prof_name}: Created {wname}")
            except Exception as e:
                print(f"[{idx}] {prof_name}: CREATE ERROR {e}")
                continue

            # N_ADDR адресов + баланс по каждому через Blockstream API
            for i in range(N_ADDR):
                k = w.new_key(change=0)  # следующий receive-адрес
                addr = k.address
                conf, unconf, total = addr_balance(url_tmpl, addr)
                print(f"  [{idx}:{prof_name}:{i}] {addr} -> total={total}")
                addr_rows.append([wname, net, prof_name, i, addr, conf, unconf, total])
                time.sleep(SLEEP)

            if not KEEP_WALLETS:
                try: wallet_delete(wname, force=True)
                except Exception: pass

    # пишем addresses CSV и summary CSV для этой сети
    addresses_csv = f"mnemonics_addresses_{net}.csv"
    summary_csv   = f"mnemonics_summary_{net}.csv"
    write_csv(addresses_csv, addr_header, addr_rows)
    summarize_to_csv(addresses_csv, summary_csv)
    print(f"[OK] Wrote {addresses_csv} and {summary_csv}")

def main():
    phrases = load_phrases(INPUT_FILE)
    if not phrases:
        print("[WARN] В файле нет фраз после фильтра комментариев/пустых строк.")
    for net in NETWORKS:
        process_network(net, phrases)
    print("\n[DONE] Оркестратор завершил работу.")

if __name__ == "__main__":
    main()
