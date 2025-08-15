import os, csv, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import List, Tuple
from mnemonic import Mnemonic
from bitcoinlib.wallets import Wallet, wallet_delete
from bitcoinlib.services.services import ServiceError

MN_FILE     = os.getenv("MN_FILE","mnemonics.txt")
OUT_CSV     = os.getenv("OUT_CSV","wallets_bitcoinlib_report.csv")
NETWORK     = os.getenv("NETWORK","bitcoin")        # 'bitcoin' | 'testnet'
WITNESS     = os.getenv("WITNESS","segwit")         # 'legacy'|'segwit'|'p2sh-segwit'|'taproot'
N_ADDR      = int(os.getenv("N_ADDR","3"))          # сколько receive-адресов проверить
MAX_WORKERS = int(os.getenv("MAX_WORKERS","6"))     # параллельных потоков скана
SALT        = os.getenv("MAPPING_SALT","")          # для приватности wallet_id

mn = Mnemonic("english")

def read_mnemonics(path:str)->List[str]:
    out=[]
    with open(path,encoding="utf-8") as f:
        for ln in f:
            s=" ".join(ln.split())
            if not s or s.startswith("#"): continue
            if mn.check(s): out.append(s)
            else: print("[WARN] BAD MNEMONIC (skip)")
    return out

def make_name(phrase:str)->str:
    return "wl_" + hashlib.sha256((SALT+phrase).encode()).hexdigest()[:10]

def process_phrase(phrase:str)->Tuple[str, str, str, Decimal, List[str], str]:
    name = make_name(phrase)
    # чистый старт (опционально): удалять старую БД кошелька
    # try: wallet_delete(name, force=True)
    # except Exception: pass

    # открыть или создать
    try:
        w = Wallet(name)
        created = False
    except Exception:
        w = Wallet.create(name, network=NETWORK, witness_type=WITNESS, keys=1, db_uri=None)
        created = True

    # сгенерировать N receive-адресов (фиксируем в БД кошелька)
    addrs=[]
    for _ in range(N_ADDR):
        k = w.new_key(change=0)
        addrs.append(k.address)

    # скан сети и баланс
    scan_err = ""
    try:
        w.scan()  # может занять время, зависит от сервиса
    except ServiceError as e:
        scan_err = f"service: {e}"
    except Exception as e:
        scan_err = f"other: {e}"

    balance = Decimal("0")
    try:
        balance = w.balance()  # Decimal в BTC
    except Exception as e:
        if not scan_err:
            scan_err = f"balance: {e}"

    return name, NETWORK, WITNESS, balance, addrs, scan_err if scan_err else ("created" if created else "opened")

def main():
    phrases = read_mnemonics(MN_FILE)
    rows=[["wallet_name","network","witness","balance_btc","addresses","note"]]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs=[ex.submit(process_phrase,p) for p in phrases]
        for fut in as_completed(futs):
            name,net,wit,bal,addrs,note = fut.result()
            rows.append([name, net, wit, str(bal), " ".join(addrs), note])
            print(f"[OK] {name} {wit} balance={bal} ({note})")
    with open(OUT_CSV,"w",newline="",encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"[DONE] wrote {OUT_CSV} (wallets: {len(rows)-1})")

if __name__=="__main__":
    main()
