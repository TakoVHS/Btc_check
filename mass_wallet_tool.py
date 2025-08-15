#!/usr/bin/env python3
# mass_wallet_tool.py
# Массовая генерация адресов (BIP44/49/84/86) и массовая проверка балансов.
# - gen-batch : генерирует адреса по "матрице" (сети/свидетельства), по аккаунтам/индексам,
#               сохраняет addresses.jsonl(+csv), xpubs.json, опц. keystore.json и mnemonic.
# - scan      : скан балансов через Blockstream API (mainnet/testnet). На "хитах" может
#               сохранять WIF (если передан keystore.json и подтверждена осознанность).
#
# НИКОГДА автоматически не печатает сид/приваты — только если явно попросишь (--include-priv).

import argparse, csv, json, os, sys, time, glob, threading, queue
from datetime import datetime
from typing import Dict, List, Tuple

import requests

from bip_utils import (
    Bip39MnemonicGenerator, Bip39SeedGenerator, Bip39WordsNum,
    Bip44, Bip49, Bip84, Bip86,
    Bip44Coins, Bip49Coins, Bip84Coins, Bip86Coins,
    Bip44Changes, BipExtKeyUtils,
)

# ---------- утилиты ----------
def now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p

def stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def write_json(path: str, obj) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _json_default(o):
    if isinstance(o, (bytes, bytearray)):
        try:
            return o.decode("utf-8")
        except Exception:
            return o.hex()
    return str(o)

def write_jsonl(path: str, rows: List[dict]) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=_json_default) + "\n")

def write_csv(path: str, rows: List[dict]) -> None:
    ensure_dir(os.path.dirname(path))
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

# ---------- маппинги ----------
def witness_to_purpose(w: str) -> int:
    return {"legacy": 44, "p2sh": 49, "segwit": 84, "tr": 86}[w]

def coin_for(witness: str, network: str):
    is_main = (network == "bitcoin")
    if witness == "legacy":
        return Bip44Coins.BITCOIN if is_main else Bip44Coins.BITCOIN_TESTNET
    if witness == "p2sh":
        return Bip49Coins.BITCOIN if is_main else Bip49Coins.BITCOIN_TESTNET
    if witness == "segwit":
        return Bip84Coins.BITCOIN if is_main else Bip84Coins.BITCOIN_TESTNET
    if witness == "tr":
        return Bip86Coins.BITCOIN if is_main else Bip86Coins.BITCOIN_TESTNET
    raise ValueError("bad witness")

def parse_accounts(s: str) -> List[int]:
    out=[]
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out

def parse_matrix(s: str) -> List[Tuple[str,str]]:
    # формат: "bitcoin:segwit,bitcoin:tr" или "testnet:legacy,bitcoin:p2sh"
    pairs=[]
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"матрица: ожидается network:witness, получено {chunk}")
        net, wit = [x.strip().lower() for x in chunk.split(":",1)]
        if net not in {"bitcoin","testnet"}:
            raise ValueError(f"network должен быть bitcoin|testnet, получено {net}")
        if wit not in {"legacy","p2sh","segwit","tr"}:
            raise ValueError(f"witness должен быть legacy|p2sh|segwit|tr, получено {wit}")
        pairs.append((net, wit))
    if not pairs:
        raise ValueError("матрица пуста")
    return pairs

def derivation_path(purpose: int, coin_type: int, account: int, change: int, index: int) -> str:
    return f"m/{purpose}'/{coin_type}'/{account}'/{change}/{index}"

# ---------- генерация ----------
def ctx_from_seed(seed: bytes, witness: str, network: str):
    if witness == "legacy":
        return Bip44.FromSeed(seed, coin_for(witness, network))
    if witness == "p2sh":
        return Bip49.FromSeed(seed, coin_for(witness, network))
    if witness == "segwit":
        return Bip84.FromSeed(seed, coin_for(witness, network))
    if witness == "tr":
        return Bip86.FromSeed(seed, coin_for(witness, network))
    raise ValueError("bad witness")

def public_xpub_for_account(seed: bytes, witness: str, network: str, account: int) -> str:
    # Возвращаем «родной» extended pub (xpub/ypub/zpub/vpub/upub/tpub в зависимости от схемы/сети)
    ctx = ctx_from_seed(seed, witness, network)
    acct = ctx.Purpose().Coin().Account(account)
    return acct.PublicKey().ToExtended()

def rows_for_combo(seed: bytes, witness: str, network: str, account: int, start: int, count: int, label: str, include_priv: bool) -> Tuple[List[dict], Dict[str,str]]:
    purpose = witness_to_purpose(witness)
    coin_type = 0 if network == "bitcoin" else 1

    ctx = ctx_from_seed(seed, witness, network)
    acct = ctx.Purpose().Coin().Account(account)

    xpub_native = acct.PublicKey().ToExtended()
    try:
        xpub_norm = BipExtKeyUtils.ToXPub(xpub_native)
    except Exception:
        xpub_norm = xpub_native

    out_rows=[]
    keystore={}  # address -> WIF
    for change_name, ch in (("receive",0), ("change",1)):
        ch_ctx = acct.Change(Bip44Changes.CHAIN_EXT if ch == 0 else Bip44Changes.CHAIN_INT)
        for i in range(start, start+count):
            node = ch_ctx.AddressIndex(i)
            addr = None
            try:
                addr = node.ToAddress()
            except Exception:
                # старые версии: через PublicKey() → ToAddress()
                addr = node.PublicKey().ToAddress()
            row = {
                "timestamp": now_iso(),
                "label": label,
                "network": network,
                "witness": witness,
                "account": account,
                "branch": change_name,
                "index": i,
                "path": derivation_path(purpose, coin_type, account, ch, i),
                "address": addr,
                "xpub": xpub_native,
                "xpub_norm": xpub_norm,
            }
            if include_priv:
                try:
                    wif = node.PrivateKey().ToWif()
                    keystore[addr] = wif
                except Exception:
                    pass
            out_rows.append(row)
    return out_rows, keystore

def cmd_gen_batch(a):
    # 1) mnemonic/seed
    if a.mnemonic:
        mnemonic = a.mnemonic.strip()
    else:
        words_num = {12: Bip39WordsNum.WORDS_NUM_12, 24: Bip39WordsNum.WORDS_NUM_24}[a.words]
        mnemonic = Bip39MnemonicGenerator().FromWordsNumber(words_num)
    seed = Bip39SeedGenerator(mnemonic).Generate(a.passphrase or "")

    # 2) каталоги
    batch_dir = os.path.join(a.out_dir, f"{stamp()}-{a.label}")
    ensure_dir(batch_dir)

    # 3) матрица/аккаунты
    matrix = parse_matrix(a.matrix)
    accounts = parse_accounts(a.accounts)

    all_rows=[]
    keystore_all={}
    xpubs_meta=[]

    # 4) генерация
    for net, wit in matrix:
        for acc in accounts:
            rows, ks = rows_for_combo(seed, wit, net, acc, a.start, a.count, a.label, a.include_priv)
            all_rows.extend(rows)
            keystore_all.update(ks)
            # сохраняем пару xpub native + нормализованный для удобства
            try:
                xp = public_xpub_for_account(seed, wit, net, acc)
                xpubs_meta.append({
                    "network": net, "witness": wit, "account": acc,
                    "xpub": xp,
                    "xpub_norm": BipExtKeyUtils.ToXPub(xp)
                })
            except Exception:
                pass

    # 5) вывод
    write_jsonl(os.path.join(batch_dir, "addresses.jsonl"), all_rows)
    write_csv(os.path.join(batch_dir, "addresses.csv"), all_rows)

    if a.write_xpubs and xpubs_meta:
        write_json(os.path.join(batch_dir, "xpubs.json"), xpubs_meta)

    if a.include_priv and keystore_all:
        write_json(os.path.join(batch_dir, "keystore.json"), keystore_all)

    if a.save_mnemonic:
        ensure_dir(os.path.dirname(a.save_mnemonic))
        with open(a.save_mnemonic, "w", encoding="utf-8") as f:
            f.write(str(mnemonic) + "\n")
        # максимально ограничим права
        try: os.chmod(a.save_mnemonic, 0o600)
        except Exception: pass

    if not a.quiet:
        print(f"[OK] batch dir: {batch_dir}")
        print(f"  rows: {len(all_rows)}")
        print(f"  files:")
        print(f"    {os.path.join(batch_dir,'addresses.jsonl')}")
        print(f"    {os.path.join(batch_dir,'addresses.csv')}")
        if a.write_xpubs: print(f"    {os.path.join(batch_dir,'xpubs.json')}")
        if a.include_priv: print(f"    {os.path.join(batch_dir,'keystore.json')}")
        if a.save_mnemonic: print(f"    {a.save_mnemonic}")
        print("\n[SAFETY] Сид/приваты сохраняются только по явному флагу (--include-priv / --save-mnemonic).")

# ---------- сканер балансов (Blockstream) ----------
def blockstream_base(network: str) -> str:
    if network == "bitcoin":
        return "https://blockstream.info/api"
    elif network == "testnet":
        return "https://blockstream.info/testnet/api"
    else:
        raise RuntimeError("Blockstream backend поддерживает только bitcoin|testnet")

def fetch_balance_blockstream(addr: str, network: str, session: requests.Session) -> dict:
    url = f"{blockstream_base(network)}/address/{addr}"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    js = r.json()
    c = js.get("chain_stats", {})
    m = js.get("mempool_stats", {})
    funded = int(c.get("funded_txo_sum", 0))
    spent  = int(c.get("spent_txo_sum", 0))
    conf_bal = funded - spent
    mem_f = int(m.get("funded_txo_sum", 0))
    mem_s = int(m.get("spent_txo_sum", 0))
    mem_delta = mem_f - mem_s
    return {
        "confirmed_sat": conf_bal,
        "mempool_delta_sat": mem_delta,
        "tx_count": int(c.get("tx_count", 0)) + int(m.get("tx_count", 0)),
        "funded_sat": funded + mem_f,
        "spent_sat": spent + mem_s,
    }

def cmd_scan(a):
    # загрузка адресов
    src = os.path.expanduser(a.src_jsonl)
    if "*" in src or "?" in src:
        cands = sorted(glob.glob(src))
        if not cands:
            print(f"не найдено по шаблону: {src}", file=sys.stderr); sys.exit(2)
        src = cands[0]
    if not os.path.isfile(src):
        print(f"нет файла: {src}", file=sys.stderr); sys.exit(2)

    rows=[]
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            # ожидаем поля address & network
            if not obj.get("address") or not obj.get("network"):
                continue
            rows.append(obj)

    # мультипоточность с rate-limit
    work_q: "queue.Queue[dict]" = queue.Queue()
    for r in rows: work_q.put(r)

    hits_dir = os.path.expanduser(a.hits_dir) if a.hits_dir else ""
    if a.write_keys_on_hit:
        if not a.keystore_json or not os.path.isfile(os.path.expanduser(a.keystore_json)):
            print("--write-keys-on-hit требует --keystore-json", file=sys.stderr); sys.exit(2)
        with open(os.path.expanduser(a.keystore_json), "r", encoding="utf-8") as f:
            keystore = json.load(f)
    else:
        keystore = {}

    out_path = os.path.expanduser(a.out_report)
    ensure_dir(os.path.dirname(out_path))
    out_f = open(out_path, "w", encoding="utf-8")

    lock = threading.Lock()
    session = requests.Session()

    def worker(tid: int):
        while True:
            try:
                r = work_q.get_nowait()
            except queue.Empty:
                return
            addr = r["address"]; net = r["network"]; wit = r.get("witness","")
            try:
                if net not in ("bitcoin","testnet"):
                    # backend не поддерживает regtest
                    result = {"confirmed_sat": 0, "mempool_delta_sat": 0, "tx_count": 0, "funded_sat": 0, "spent_sat": 0}
                else:
                    result = fetch_balance_blockstream(addr, net, session)
                conf = int(result["confirmed_sat"])
                memd = int(result["mempool_delta_sat"])
                total = conf + (0 if a.confirmed_only else memd)

                out = {
                    "timestamp": now_iso(),
                    "address": addr,
                    "network": net,
                    "witness": wit,
                    "account": r.get("account"),
                    "branch": r.get("branch"),
                    "index": r.get("index"),
                    "path": r.get("path"),
                    "confirmed_sat": conf,
                    "mempool_delta_sat": memd,
                    "effective_sat": conf if a.confirmed_only else total,
                    "tx_count": result["tx_count"],
                }

                is_hit = (out["effective_sat"] > 0)
                if is_hit and a.write_keys_on_hit and a.i_understand and hits_dir:
                    wif = keystore.get(addr)
                    if wif:
                        dst = os.path.join(hits_dir, net, wit)
                        ensure_dir(dst)
                        with open(os.path.join(dst, f"{addr}.wif.txt"), "w", encoding="utf-8") as fw:
                            fw.write(wif + "\n")

                with lock:
                    out_f.write(json.dumps(out, ensure_ascii=False) + "\n")
                    out_f.flush()

            except Exception as e:
                with lock:
                    out_f.write(json.dumps({
                        "timestamp": now_iso(),
                        "address": addr, "network": net,
                        "error": str(e),
                    }, ensure_ascii=False) + "\n")
                    out_f.flush()
            finally:
                time.sleep(max(0.0, a.delay_ms/1000.0))
                work_q.task_done()

    threads=[]
    for i in range(max(1, a.workers)):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    out_f.close()
    print(f"[OK] scan report → {out_path}")

# ---------- CLI ----------
def make_parser():
    p = argparse.ArgumentParser(description="Mass wallet generator & scanner (bip-utils + requests)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # gen-batch
    g = sub.add_parser("gen-batch", help="Массовая генерация адресов по матрице")
    g.add_argument("--matrix", required=True, help="network:witness,... напр. bitcoin:segwit,bitcoin:tr")
    g.add_argument("--accounts", default="0", help="список аккаунтов через запятую, напр. 0 или 0,1,2")
    g.add_argument("--start", type=int, default=0)
    g.add_argument("--count", type=int, default=20)
    g.add_argument("--label", default="batch")
    g.add_argument("--out-dir", default="./mass_exports")
    g.add_argument("--write-xpubs", action="store_true")
    g.add_argument("--include-priv", action="store_true", help="сохранить keystore.json (адрес→WIF)")
    g.add_argument("--save-mnemonic", default="", help="путь для сохранения сид-фразы (600)")
    g.add_argument("--mnemonic", default="", help="использовать заданный сид вместо генерации")
    g.add_argument("--words", type=int, default=12, choices=[12,24], help="кол-во слов при генерации")
    g.add_argument("--passphrase", default="", help="BIP39 passphrase (опц.)")
    g.add_argument("--quiet", action="store_true")

    # scan
    s = sub.add_parser("scan", help="Массовая проверка балансов (Blockstream)")
    s.add_argument("--src-jsonl", required=True, help="addresses.jsonl (из gen-batch) или шаблон")
    s.add_argument("--out-report", required=True, help="файл jsonl для результатов")
    s.add_argument("--backend", default="blockstream", choices=["blockstream"], help="пока только blockstream")
    s.add_argument("--confirmed-only", action="store_true", help="не учитывать mempool")
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--delay-ms", type=int, default=120, help="задержка между запросами каждым потоком")
    s.add_argument("--hits-dir", default="", help="куда складывать ключи на «хитах» (если разрешено)")
    s.add_argument("--write-keys-on-hit", action="store_true", help="писать WIF при наличии keystore.json")
    s.add_argument("--i-understand", action="store_true", help="подтверждение осознанности")
    s.add_argument("--keystore-json", default="", help="keystore.json из gen-batch (адрес→WIF)")

    return p

def main():
    p = make_parser()
    a = p.parse_args()
    if a.cmd == "gen-batch":
        cmd_gen_batch(a)
    elif a.cmd == "scan":
        cmd_scan(a)
    else:
        p.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
