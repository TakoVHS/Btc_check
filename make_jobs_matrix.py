#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

# матрица
NETWORKS = ["bitcoin","testnet","regtest"]
WITNESSES = ["legacy","p2sh-segwit","segwit","tr"]
ACCOUNTS = [0,1]

def out_dir(net, wit, acc): return f"./mass_exports/{net}/{wit}/a{acc}"
def xpub_file(net, wit, acc): return f"./mass_exports/xpubs/{net}/{wit}/a{acc}.xpub"
def wallet_name(prefix, wit, acc): return f"{prefix}_{wit}_a{acc}"

def gen_job(prefix, net, wit, acc, count):
    return {
        "type": "gen",
        "wallet": wallet_name(prefix, wit, acc),
        "network": net,
        "witness": wit,
        "account": acc,
        "branch": "both",
        "start": 0,
        "count": count,
        "precreate": count,
        "out_dir": out_dir(net,wit,acc),
        "format": "csv,jsonl",
        "xpub_file": xpub_file(net,wit,acc)
    }

def ver_job(prefix, net, wit, acc, branch, count):
    return {
        "type": "verify",
        "wallet": wallet_name(prefix, wit, acc),
        "xpub_file": xpub_file(net,wit,acc),
        "network": net,
        "witness": wit,
        "branch": branch,
        "start": 0,
        "count": count,
        "compare_from_latest_gen": True
    }

def main():
    jobs=[]
    for net in NETWORKS:
        for wit in WITNESSES:
            for acc in ACCOUNTS:
                cnt = 10 if acc==0 else 5
                jobs.append(gen_job("lab", net, wit, acc, cnt))
                jobs.append(ver_job("lab", net, wit, acc, "receive", cnt))
                jobs.append(ver_job("lab", net, wit, acc, "change",  cnt))
    print(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
