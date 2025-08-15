import csv, time, requests, sys
from bitcoinlib.wallets import Wallet, wallet_delete
from mnemonic import Mnemonic

INPUT_FILE  = "mnemonics.txt"
OUTPUT_FILE = "mnemonics_report.csv"

NETWORK = "bitcoin"      # 'bitcoin' | 'testnet'
WITNESS = "segwit"       # 'legacy' | 'segwit' | 'p2sh-segwit' | 'taproot'
PURPOSE = 84             # 44=legacy, 49=p2sh-segwit, 84=segwit, 86=taproot
N_ADDR = 3               # сколько адресов выводить на фразу
SLEEP = 0.8              # пауза между запросами к API

API_URL = (
    "https://blockstream.info/api/address/{}"
    if NETWORK == "bitcoin"
    else "https://blockstream.info/testnet/api/address/{}"
)

def addr_balance(addr: str):
    try:
        r = requests.get(API_URL.format(addr), timeout=12)
        r.raise_for_status()
        data = r.json()
        cs = data.get("chain_stats", {})
        ms = data.get("mempool_stats", {})
        confirmed = cs.get("funded_txo_sum", 0) - cs.get("spent_txo_sum", 0)
        unconfirmed = ms.get("funded_txo_sum", 0) - ms.get("spent_txo_sum", 0)
        return confirmed, unconfirmed, confirmed + unconfirmed
    except Exception as e:
        return f"ERR: {e}", "", ""

def main():
    # читаем фразы
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except FileNotFoundError:
        print(f"[ERR] Нет файла {INPUT_FILE}.")
        sys.exit(1)

    mnemo = Mnemonic("english")
    rows = [["wallet_name","address_index","address","confirmed_sats","unconfirmed_sats","total_sats"]]

    for idx, phrase in enumerate(lines, 1):
        # валидируем BIP-39: 12/15/18/21/24 слов из словаря, корректная контрольная сумма
        if not mnemo.check(phrase):
            print(f"[{idx}] BAD MNEMONIC")
            continue

        name = f"mnemonic_{idx}"

        # чистый старт для повторных прогонов
        try:
            wallet_delete(name, force=True)
        except Exception:
            pass

        # создаём кошелёк из сид-фразы (BIP84 SegWit)
        try:
            w = Wallet.create(
                name,
                keys=phrase,
                network=NETWORK,
                witness_type=WITNESS,
                purpose=PURPOSE,
                account_id=0
            )
            print(f"[{idx}] Created wallet: {name}")
        except Exception as e:
            print(f"[{idx}] CREATE ERROR: {e}")
            continue

        # берём N_ADDR приёмных адресов
        for i in range(N_ADDR):
            k = w.new_key(change=0)   # следующий receive-адрес
            addr = k.address
            conf, unconf, total = addr_balance(addr)
            print(f"  [{idx}:{i}] {addr} -> total={total}")
            rows.append([name, i, addr, conf, unconf, total])
            time.sleep(SLEEP)

    # пишем отчёт всегда (как минимум с заголовком)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"[OK] Wrote {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
