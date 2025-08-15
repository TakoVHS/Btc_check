#!/usr/bin/env python3
# wallet_tool.py v7
# Генерация адресов (BIP44/49/84/86), проверка из xpub, работа с Descriptor/Miniscript (embit).
# Устойчив к разным версиям bitcoinlib, аккуратные ошибки, без утечек приватных данных по умолчанию.

import argparse, csv, json, os, sys, time, re, glob
from datetime import datetime
from typing import List, Optional, Tuple

# --- внешние либы ---
from bitcoinlib.wallets import Wallet, wallet_exists
from bitcoinlib.wallets import WalletError as _WalletError

try:
    from bip_utils import (
        Bip44, Bip49, Bip84, Bip86,
        Bip44Coins, Bip49Coins, Bip84Coins, Bip86Coins,
        Bip44Changes, BipExtKeyUtils,
    )
    HAS_BIP = True
except Exception:
    HAS_BIP = False

try:
    from embit.descriptor import Descriptor
    from embit.networks import NETWORKS
    HAS_EMBIT = True
except Exception:
    HAS_EMBIT = False

# ---------- утилиты ----------
def ts_iso(): return datetime.now().astimezone().isoformat()
def ensure_dir(p): os.makedirs(p, exist_ok=True); return p

def is_tty():
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")

def color(s, c):
    if not is_tty(): return s
    codes = dict(g="\033[32m", y="\033[33m", r="\033[31m", b="\033[34m", dim="\033[2m", reset="\033[0m")
    return f"{codes.get(c,'')}{s}{codes['reset']}"

def out_base(out_dir, wallet, network, witness):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"addresses-{stamp}-{wallet}-{network}-{witness}"
    return os.path.join(out_dir, base)

def write_csv(path, rows):
    ensure_dir(os.path.dirname(path))
    if not rows:
        open(path, "w").close(); return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

def _json_default(o):
    if isinstance(o, (bytes, bytearray)):
        try: return o.decode("utf-8")
        except Exception: return o.hex()
    return str(o)

def write_jsonl(path, rows_iter):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        for r in rows_iter:
            f.write(json.dumps(r, ensure_ascii=False, default=_json_default) + "\n")

def split_writer(base_path_no_ext: str, fmt: str, split: int):
    """
    Возвращает генератор write(row) / close() для построчной записи с разбиением на части.
    """
    assert fmt in ("csv", "jsonl")
    state = {"n":0, "part":1, "fh":None, "writer":None, "wrote_header":False}

    def open_new():
        ensure_dir(os.path.dirname(base_path_no_ext))
        suf = f".part{state['part']:02d}"
        path = base_path_no_ext + suf + ("."+fmt)
        fh = open(path, "w", newline="" if fmt=="csv" else None, encoding="utf-8")
        state["fh"] = fh
        state["wrote_header"] = False
        return path

    def write_row(row, header_keys=None):
        nonlocal fmt
        if state["fh"] is None:
            open_new()
        if split and state["n"]>0 and state["n"]%split==0:
            state["fh"].close(); state["part"] += 1; open_new()
        if fmt == "csv":
            if not state["wrote_header"]:
                writer = csv.DictWriter(state["fh"], fieldnames=list(header_keys or row.keys()))
                state["writer"] = writer
                writer.writeheader()
                state["wrote_header"] = True
            state["writer"].writerow(row)
        else:
            state["fh"].write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
        state["n"] += 1

    def close():
        if state["fh"]: state["fh"].close()

    return write_row, close

def witness_to_purpose(w): return {"legacy":44, "p2sh-segwit":49, "segwit":84, "tr":86}[w]
def network_to_coin_type(network): return 0 if network == "bitcoin" else 1
def derivation_path_fallback(witness, network, account, change, index):
    return f"m/{witness_to_purpose(witness)}'/{network_to_coin_type(network)}'/{account}'/{change}/{index}"

def _bitcoinlib_witness(w: str) -> str:
    # bitcoinlib использует 'taproot' вместо 'tr'
    return {"legacy":"legacy","p2sh-segwit":"p2sh-segwit","segwit":"segwit","tr":"taproot"}[w]

def _pretty_type(x):
    return f"{type(x).__name__}({len(x)} bytes)" if isinstance(x,(bytes,bytearray)) else f"{type(x).__name__}"

def safe_get_xpub(w: Wallet, account_id: int = 0) -> str:
    last_exc = None
    getters = [
        lambda: getattr(w, "account_xpub")(),
        lambda: w.account().key_public,
        lambda: w.account(account_id).key_public,
        lambda: getattr(getattr(w, "account", None)(), "key_public", None),
    ]
    for g in getters:
        try:
            xp = g()
            if xp:
                if isinstance(xp, (bytes, bytearray)):
                    print(color(f"[warn] bitcoinlib вернул {_pretty_type(xp)} вместо xpub; сохраняю hex", "y"), file=sys.stderr)
                    return xp.hex()
                return str(xp).strip()
        except TypeError:
            try:
                xp = w.account(account_id).key_public
                if xp: return str(xp if not isinstance(xp,(bytes,bytearray)) else xp.hex()).strip()
            except Exception as e:
                last_exc = e
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"Не удалось получить xpub из bitcoinlib: {last_exc}")

def key_by_index(w: Wallet, account: int, change: int, idx: int, network: str):
    try: return w.address_index(idx, account_id=account, change=change, network=network)
    except Exception: pass
    try: return w.key_for_path([change, idx], account_id=account, change=change, network=network)
    except TypeError:
        try: return w.key_for_path([change, idx], account_id=account, change=change)
        except Exception: pass
    except Exception: pass
    for kw in ({"change":change, "index":idx},
               {"change":change, "address_index":idx},
               {"key_index":idx, "change":change},
               {"address_index":idx}):
        try: return w.get_key(**kw)
        except Exception: continue
    raise RuntimeError(f"Не удалось получить ключ index={idx} change={change}")

def precreate_keys(w: Wallet, account: int, start: int, count: int, network: str):
    for ch in (0,1):
        target = start+count-1
        created = 0
        while True:
            try:
                _ = w.address_index(target, account_id=account, change=ch, network=network)
                break
            except Exception:
                pass
            advanced = False
            for method in ("new_key", "new_address"):
                if hasattr(w, method):
                    try: getattr(w, method)(change=ch, network=network); advanced=True; created+=1
                    except Exception: pass
            if not advanced: break
        if created and is_tty():
            print(color(f"[precreate] account={account} change={ch} создано ~{created} ключей", "dim"))

# ---------- bip_utils ----------
def coin_for(witness: str, network: str):
    is_main = (network == "bitcoin")
    if witness == "legacy": return Bip44Coins.BITCOIN if is_main else Bip44Coins.BITCOIN_TESTNET
    if witness == "p2sh-segwit": return Bip49Coins.BITCOIN if is_main else Bip49Coins.BITCOIN_TESTNET
    if witness == "segwit": return Bip84Coins.BITCOIN if is_main else Bip84Coins.BITCOIN_TESTNET
    if witness == "tr": return Bip86Coins.BITCOIN if is_main else Bip86Coins.BITCOIN_TESTNET
    raise ValueError("bad witness")

def derive_with_bip_utils(xpub: str, witness: str, network: str, change: int, index: int) -> str:
    if not HAS_BIP:
        raise RuntimeError("bip_utils не установлен: `pip install bip-utils`")
    coin = coin_for(witness, network)
    try:
        norm_xpub = BipExtKeyUtils.ToXPub(xpub) if xpub else xpub
    except Exception as e:
        raise RuntimeError(f"Требуется extended public key (xpub/tpub/...); получено '{str(xpub)[:16]}…'") from e
    if witness == "legacy": ctx = Bip44.FromExtendedKey(norm_xpub, coin)
    elif witness == "p2sh-segwit": ctx = Bip49.FromExtendedKey(norm_xpub, coin)
    elif witness == "segwit": ctx = Bip84.FromExtendedKey(norm_xpub, coin)
    else: ctx = Bip86.FromExtendedKey(norm_xpub, coin)
    chg = ctx.Change(Bip44Changes.CHAIN_EXT if change==0 else Bip44Changes.CHAIN_INT)
    try: return chg.AddressIndex(index).ToAddress()
    except Exception: return chg.AddressIndex(index).PublicKey().ToAddress()

def verify_xpub_addresses(xpub: str, witness: str, network: str, branch: str, start: int, count: int) -> list:
    todo=[]
    if branch in ("receive","both"): todo.append(("receive",0))
    if branch in ("change","both"):  todo.append(("change",1))
    out=[]
    for name, change in todo:
        for i in range(start, start+count):
            addr = derive_with_bip_utils(xpub, witness, network, change, i)
            out.append({"branch":name, "index":i, "address":addr, "network":network, "witness":witness})
    return out

# ---------- descriptor/miniscript (embit) ----------
def _net_obj(network: str):
    if network == "bitcoin": return NETWORKS["main"]
    if network in ("testnet","regtest"): return NETWORKS["test"]
    raise ValueError("bad network")

def derive_from_descriptor(descriptor: str, network: str, branch: str, start: int, count: int, label="desc"):
    if not HAS_EMBIT:
        raise RuntimeError("embit не установлен: `pip install embit`")
    desc = Descriptor.from_string(descriptor.strip())
    net = _net_obj(network)
    dstr = descriptor.replace(" ", "")
    has_both = re.search(r"/\{0,1\}/\*", dstr) is not None
    force_ch = None
    if re.search(r"/0/\*$", dstr): force_ch = 0
    if re.search(r"/1/\*$", dstr): force_ch = 1
    branches = []
    if branch == "auto":
        if has_both: branches = [("receive",0),("change",1)]
        elif force_ch is not None: branches = [("receive",force_ch)] if force_ch==0 else [("change",1)]
        else: branches = [("receive",0)]
    else:
        if branch in ("receive","both"): branches.append(("receive",0))
        if branch in ("change","both"):  branches.append(("change",1))
    for name,ch in branches:
        for i in range(start, start+count):
            ctx = desc.derive(i, change=ch)
            addr = ctx.address(net)
            yield {
                "timestamp": ts_iso(),
                "wallet": label,
                "network": network,
                "witness": "desc",
                "account": None,
                "branch": name,
                "index": i,
                "path": None,
                "address": addr,
                "xpub": None
            }

# ---------- helpers ----------
def parse_accounts_range(s: str) -> List[int]:
    if not s: return []
    if ":" in s:
        a,b = s.split(":",1)
        a = int(a); b = int(b)
        if b < a: raise ValueError("--accounts-range: end < start")
        return list(range(a, b+1))
    return [int(x) for x in s.split(",") if x.strip()]

def parse_matrix(s: str) -> List[Tuple[str,str]]:
    pairs=[]
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk: continue
        if ":" not in chunk: raise ValueError(f"matrix item '{chunk}' без ':'")
        net, wit = [x.strip().lower() for x in chunk.split(":",1)]
        if net not in {"bitcoin","testnet","regtest"}: raise ValueError(f"network? {net}")
        if wit not in {"legacy","p2sh-segwit","segwit","tr"}: raise ValueError(f"witness? {wit}")
        pairs.append((net, wit))
    return pairs

def find_latest_export(out_dir: str, wallet: str, network: str, witness: str, prefer="jsonl") -> Optional[str]:
    out_dir = os.path.expanduser(out_dir)
    if not os.path.isdir(out_dir): return None
    pattern = os.path.join(out_dir, f"addresses-*-{wallet}-{network}-{witness}.*")
    cands = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not cands: return None
    for p in cands:
        if p.endswith(prefer): return p
    return cands[0]

def extract_branch_subset(path: str, branch: str, start: int, count: int) -> List[str]:
    addrs=[]
    if path.endswith(".jsonl"):
        with open(path,"r",encoding="utf-8") as f:
            for line in f:
                try: obj=json.loads(line)
                except Exception: continue
                if branch!="both" and obj.get("branch")!=branch: continue
                addrs.append(obj.get("address"))
    elif path.endswith(".csv"):
        with open(path,"r",encoding="utf-8") as f:
            rdr=csv.DictReader(f)
            for row in rdr:
                if branch!="both" and row.get("branch")!=branch: continue
                addrs.append(row.get("address"))
    else:
        addrs=[ln.strip() for ln in open(path,"r",encoding="utf-8").read().splitlines() if ln.strip()]
    return addrs[start:start+count]

# ---------- CLI ----------
def make_parser():
    p = argparse.ArgumentParser(description="Wallet tool (BIP44/49/84/86 + Descriptor/Miniscript)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="Генерация адресов + CSV/JSONL (stream/split)")
    g.add_argument("--wallet", default="demo_wallet")
    g.add_argument("--network", default="testnet", choices=["bitcoin","testnet","regtest"])
    g.add_argument("--witness", default="segwit", choices=["legacy","p2sh-segwit","segwit","tr"])
    g.add_argument("--branch", default="receive", choices=["receive","change","both"])
    g.add_argument("--start", type=int, default=0)
    g.add_argument("--count", type=int, default=5)
    g.add_argument("--resume-from", type=int, default=0, dest="resume_from")
    g.add_argument("--account", type=int, default=0)
    g.add_argument("--accounts-range", default="")
    g.add_argument("--precreate", type=int, default=0, help="Прогреть ключи до N индексов")
    g.add_argument("--out-dir", default=os.path.expanduser("./exports"))
    g.add_argument("--format", default="csv,jsonl")
    g.add_argument("--csv-only", action="store_true")
    g.add_argument("--jsonl-only", action="store_true")
    g.add_argument("--split", type=int, default=0, help="Разбивать файлы каждые N строк")
    g.add_argument("--xpub-file", default="")
    g.add_argument("--matrix", default="", help="network:witness,... напр. bitcoin:legacy,testnet:segwit,regtest:tr")
    g.add_argument("--progress", action="store_true")
    g.add_argument("--quiet", action="store_true")

    v = sub.add_parser("verify", help="Проверка адресов из xpub через bip_utils")
    v.add_argument("--xpub", required=True)
    v.add_argument("--witness", required=True, choices=["legacy","p2sh-segwit","segwit","tr"])
    v.add_argument("--network", required=True, choices=["bitcoin","testnet","regtest"])
    v.add_argument("--branch", default="receive", choices=["receive","change","both"])
    v.add_argument("--start", type=int, default=0)
    v.add_argument("--count", type=int, default=5)
    v.add_argument("--compare-file", default="")

    d1 = sub.add_parser("desc-derive", help="Адреса из дескриптора (Miniscript)")
    d1.add_argument("--descriptor", default="")
    d1.add_argument("--descriptor-file", default="")
    d1.add_argument("--network", required=True, choices=["bitcoin","testnet","regtest"])
    d1.add_argument("--branch", default="auto", choices=["auto","receive","change","both"])
    d1.add_argument("--start", type=int, default=0)
    d1.add_argument("--count", type=int, default=5)
    d1.add_argument("--out-dir", default=os.path.expanduser("./exports"))
    d1.add_argument("--format", default="csv,jsonl")
    d1.add_argument("--label", default="desc")

    d2 = sub.add_parser("desc-verify", help="Проверка адресов из дескриптора (Miniscript)")
    d2.add_argument("--descriptor", default="")
    d2.add_argument("--descriptor-file", default="")
    d2.add_argument("--network", required=True, choices=["bitcoin","testnet","regtest"])
    d2.add_argument("--branch", default="auto", choices=["auto","receive","change","both"])
    d2.add_argument("--start", type=int, default=0)
    d2.add_argument("--count", type=int, default=5)
    d2.add_argument("--compare-file", default="", help="Эталон (CSV/JSONL/PLAIN) или auto")
    d2.add_argument("--wallet", default="", help="Для compare-file=auto: имя кошелька (label)")

    return p

# ---------- команды ----------
def cmd_gen(a):
    # форматы
    fmt_csv = ("csv" in a.format) or a.csv_only
    fmt_jsonl = ("jsonl" in a.format) or a.jsonl_only
    if a.csv_only: fmt_jsonl = False
    if a.jsonl_only: fmt_csv = False
    if not (fmt_csv or fmt_jsonl):
        print("Нечего писать: форматы выключены", file=sys.stderr); sys.exit(2)

    # матрица сетей/типов
    combos = [(a.network, a.witness)]
    if a.matrix.strip():
        combos = parse_matrix(a.matrix)

    accounts = [a.account] if not a.accounts_range else parse_accounts_range(a.accounts_range)

    wrote=[]
    for net, wit in combos:
        w = Wallet(a.wallet) if wallet_exists(a.wallet) else Wallet.create(a.wallet, network=net, witness_type=_bitcoinlib_witness(wit))
        if a.precreate > 0:
            precreate_keys(w, accounts[0], a.start, max(a.count, a.precreate), net)

        xpub = safe_get_xpub(w, account_id=accounts[0])

        # базовые пути
        base = out_base(ensure_dir(a.out_dir), w.name, net, wit)

        # сплит-писатели
        csv_write, csv_close = (lambda r, hk=None: None, lambda: None)
        jsonl_write, jsonl_close = (lambda r, hk=None: None, lambda: None)
        if fmt_csv:
            csv_write, csv_close = split_writer(base, "csv", a.split)
        if fmt_jsonl:
            jsonl_write, jsonl_close = split_writer(base, "jsonl", a.split)

        # печать заголовка
        if not a.quiet:
            print(color(f"[OK] wallet='{w.name}' network='{net}' witness='{wit}' branch='{a.branch}'", "g"))
            print("xpub/ypub/zpub/tpub/upub/vpub:", xpub)

        total = 0
        t0 = time.time()

        todo=[]
        if a.branch in ("receive","both"): todo.append(("receive",0))
        if a.branch in ("change","both"):  todo.append(("change",1))

        for acct in accounts:
            for name, ch in todo:
                start = a.start + a.resume_from
                end = a.start + a.count
                for i in range(start, end):
                    key = key_by_index(w, acct, ch, i, net)
                    path = getattr(key, "path", None)
                    if not (isinstance(path,str) and path.startswith("m/")):
                        path = derivation_path_fallback(wit, net, acct, ch, i)
                    row = {
                        "timestamp": ts_iso(),"wallet": w.name,"network": net,"witness": wit,
                        "account": acct,"branch": name,"index": i,"path": path,
                        "address": key.address,"xpub": xpub
                    }
                    if fmt_csv:   csv_write(row, header_keys=list(row.keys()))
                    if fmt_jsonl: jsonl_write(row, header_keys=None)
                    total += 1
                    if a.progress and total % 1000 == 0:
                        dt = max(1e-6, time.time()-t0)
                        rate = total/dt
                        remaining = (len(accounts)*len(todo)*(end-start) - (total)) / max(1e-6, rate)
                        print(color(f"[prog] {total} rows, {rate:,.0f} r/s, ETA {remaining/60:,.1f} min", "dim"))

        csv_close(); jsonl_close()

        if a.xpub_file:
            xp = os.path.abspath(os.path.expanduser(a.xpub_file))
            ensure_dir(os.path.dirname(xp))
            with open(xp, "w", encoding="utf-8") as f: f.write(str(xpub).strip()+"\n")
            wrote.append(xp)

        if not a.quiet:
            print(color(f"Файлы базово: {base}.csv / {base}.jsonl (или части .partNN)", "dim"))

    if wrote and not a.quiet:
        print("Дополнительно сохранено:"); [print("  ", p) for p in wrote]
    if not a.quiet:
        print(color("\n[SAFETY] Скрипт не выводит сид/xprv/WIF.", "y"))

def read_expected_addresses(path_or_file: str) -> List[str]:
    p = os.path.expanduser(path_or_file)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"compare_file не найден: {p}")
    if p.endswith(".jsonl"):
        out=[]
        with open(p,"r",encoding="utf-8") as f:
            for line in f:
                try: obj=json.loads(line); 
                except Exception: continue
                addr = obj.get("address") or obj.get("addr")
                if addr: out.append(addr)
        return out
    if p.endswith(".csv"):
        out=[]
        with open(p,"r",encoding="utf-8") as f:
            rdr=csv.DictReader(f)
            for row in rdr:
                addr = row.get("address") or row.get("addr")
                if addr: out.append(addr)
        return out
    return [ln.strip() for ln in open(p,"r",encoding="utf-8").read().splitlines() if ln.strip()]

def compare_and_exit(expected: List[str], got: List[str]):
    mism=[]
    for i,g in enumerate(got):
        exp = expected[i] if i < len(expected) else None
        if exp is not None and exp != g: mism.append((i,exp,g))
    if mism:
        print("\n"+color("❌ Несовпадения:", "r"))
        for i,e,g in mism: print(f"  index {i}: expected {e}, got {g}")
        sys.exit(1)
    print("\n"+color("✅ Совпадает с эталоном","g"))

def cmd_verify(a):
    try:
        import bip_utils as _b
        if is_tty():
            print(color(f"[debug] bip_utils={getattr(_b,'__version__','?')} from {_b.__file__}", "dim"))
    except Exception as e:
        print(f"❌ bip_utils импорт не удался: {e}", file=sys.stderr); sys.exit(2)
    derived = verify_xpub_addresses(a.xpub, a.witness, a.network, a.branch, a.start, a.count)
    for d in derived: print(f"{d['branch']}[{d['index']}] -> {d['address']} ({d['network']}/{d['witness']})")
    if a.compare_file:
        expected = read_expected_addresses(a.compare_file)
        compare_and_exit(expected, [d["address"] for d in derived])

def cmd_desc_derive(a):
    desc = a.descriptor.strip() or open(os.path.expanduser(a.descriptor_file),"r",encoding="utf-8").read().strip()
    rows = derive_from_descriptor(desc, a.network, a.branch, a.start, a.count, label=a.label)
    base = out_base(ensure_dir(a.out_dir), a.label, a.network, "desc")
    fmt_csv = "csv" in a.format
    fmt_jsonl = "jsonl" in a.format
    wrote=[]
    rows_iter = list(rows)
    if fmt_csv:   write_csv(base+".csv", rows_iter); wrote.append(base+".csv")
    if fmt_jsonl: write_jsonl(base+".jsonl", rows_iter); wrote.append(base+".jsonl")
    print(color(f"[OK] desc-derive {a.network}/{a.branch}: {len(rows_iter)} адресов", "g"))
    if wrote: print("Файлы:"); [print("  ", p) for p in wrote]

def cmd_desc_verify(a):
    desc = a.descriptor.strip() or open(os.path.expanduser(a.descriptor_file),"r",encoding="utf-8").read().strip()
    rows_iter = list(derive_from_descriptor(desc, a.network, a.branch, a.start, a.count, label="desc"))
    got = [r["address"] for r in rows_iter]
    if a.compare_file and a.compare_file != "auto":
        expected = read_expected_addresses(a.compare_file)
    elif a.compare_file == "auto":
        if not a.wallet:
            print("compare_file=auto требует --wallet", file=sys.stderr); sys.exit(2)
        latest = find_latest_export("./exports", a.wallet, a.network, "desc", prefer="jsonl")
        if not latest:
            print(f"Не найден свежий экспорт для wallet={a.wallet} network={a.network} witness=desc", file=sys.stderr); sys.exit(2)
        expected = extract_branch_subset(latest, "receive" if a.branch=="auto" else a.branch, a.start, a.count)
        print(color(f"[auto] Эталон: {latest}", "dim"))
    else:
        for r in rows_iter: print(f"{r['branch']}[{r['index']}] {r['address']}"); return
    compare_and_exit(expected, got)

def main():
    # предохранитель: локальные тени bip_utils?
    if "bip_utils" in sys.modules:
        p = getattr(sys.modules["bip_utils"], "__file__", "")
        if p and "site-packages" not in (p or ""):
            print(color(f"[warn] bip_utils импортирован из '{p}', а не из site-packages. Удалите/переименуйте локальные файлы.", "y"), file=sys.stderr)
    p = make_parser(); a = p.parse_args()
    if a.cmd == "gen": cmd_gen(a)
    elif a.cmd == "verify": cmd_verify(a)
    elif a.cmd == "desc-derive": cmd_desc_derive(a)
    elif a.cmd == "desc-verify": cmd_desc_verify(a)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(130)
