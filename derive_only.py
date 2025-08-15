import csv, hashlib, sys
from typing import List, Tuple
from mnemonic import Mnemonic
from bip_utils import (
    Bip44, Bip49, Bip84, Bip86,
    Bip44Coins, Bip49Coins, Bip84Coins, Bip86Coins,
    Bip44Changes,
)

# ========== КОНФИГ ==========
INPUT_FILE = "mnemonics.txt"
OUTPUT_CSV = "derived_addresses_only.csv"
NETWORKS   = ["bitcoin", "testnet"]
PROFILES: List[Tuple[str,str]] = [
    ("bip44_legacy",  "bip44"),
    ("bip49_p2sh",    "bip49"),
    ("bip84_segwit",  "bip84"),
    ("bip86_taproot", "bip86"),
]
ACCOUNT = 0
CHANGE  = Bip44Changes.CHAIN_EXT  # receive chain
N_ADDR  = 3
# ===========================

def read_phrases(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except FileNotFoundError:
        print(f"[ERR] Нет файла {path}")
        sys.exit(1)

def coin_for(net: str, scheme: str):
    if scheme == "bip44":
        return Bip44Coins.BITCOIN if net=="bitcoin" else Bip44Coins.BITCOIN_TESTNET
    if scheme == "bip49":
        return Bip49Coins.BITCOIN if net=="bitcoin" else Bip49Coins.BITCOIN_TESTNET
    if scheme == "bip84":
        return Bip84Coins.BITCOIN if net=="bitcoin" else Bip84Coins.BITCOIN_TESTNET
    if scheme == "bip86":
        return Bip86Coins.BITCOIN if net=="bitcoin" else Bip86Coins.BITCOIN_TESTNET
    raise ValueError("Unknown scheme")

def ctx_for(mnemonic: str, net: str, scheme: str):
    coin = coin_for(net, scheme)
    if scheme == "bip44":
        root = Bip44.FromMnemonic(mnemonic, coin)
    elif scheme == "bip49":
        root = Bip49.FromMnemonic(mnemonic, coin)
    elif scheme == "bip84":
        root = Bip84.FromMnemonic(mnemonic, coin)
    elif scheme == "bip86":
        root = Bip86.FromMnemonic(mnemonic, coin)
    else:
        raise ValueError("Unknown scheme")
    acc  = root.Account(ACCOUNT)
    recv = acc.Change(CHANGE)
    return recv

def main():
    phrases = read_phrases(INPUT_FILE)
    mn      = Mnemonic("english")

    rows = [["wallet_id","network","profile","address_index","address","path_hint"]]

    for idx, phrase in enumerate(phrases, 1):
        if not mn.check(phrase):
            print(f"[{idx}] BAD MNEMONIC (пропущена)")
            continue

        short = hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8]

        for net in NETWORKS:
            for prof_name, scheme in PROFILES:
                try:
                    chain = ctx_for(phrase, net, scheme)
                except Exception as e:
                    print(f"[{idx}] {net} {prof_name}: ошибка инициализации: {e}")
                    continue
                for i in range(N_ADDR):
                    try:
                        node = chain.AddressIndex(i)
                        addr = node.PublicKey().ToAddress()
                        purpose = {"bip44":44,"bip49":49,"bip84":84,"bip86":86}[scheme]
                        path_hint = f"m/{purpose}'/*'/{ACCOUNT}'/0/{i}"
                        rows.append([short, net, prof_name, i, addr, path_hint])
                    except Exception as e:
                        print(f"[{idx}] {net} {prof_name}:{i} ошибка: {e}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"[OK] Записано: {OUTPUT_CSV} (строк: {len(rows)-1})")

if __name__ == "__main__":
    main()
