#!/usr/bin/env python3
# show_hits.py — просмотрщик отчётов сканера (JSONL), теплокарта по аккаунтам, фильтры и WIF-экстрактор.

import argparse, os, sys, json, csv, glob
from datetime import datetime
from typing import List, Dict, Any, Optional

def is_tty():
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")

def color(s, c):
    if not is_tty(): return s
    codes = dict(g="\033[32m", y="\033[33m", r="\033[31m", b="\033[34m", dim="\033[2m", reset="\033[0m")
    return f"{codes.get(c,'')}{s}{codes['reset']}"

def read_jsonl(path: str) -> List[Dict[str,Any]]:
    with open(path,"r",encoding="utf-8") as f:
        out=[]
        for line in f:
            try: out.append(json.loads(line))
            except Exception: pass
    return out

def sat_to_btc(sat: int) -> float:
    try: return int(sat)/1e8
    except Exception: return 0.0

def find_report_auto() -> Optional[str]:
    # Находим самый свежий *.jsonl в ./scan_reports
    roots = ["./scan_reports", "./reports", "."]
    cands=[]
    for root in roots:
        if os.path.isdir(root):
            cands += glob.glob(os.path.join(root, "*.jsonl"))
    if not cands: return None
    return sorted(cands, key=os.path.getmtime, reverse=True)[0]

def parse_accounts(s: str) -> Optional[List[int]]:
    if not s: return None
    out=[]
    for chunk in s.split(","):
        chunk=chunk.strip()
        if not chunk: continue
        out.append(int(chunk))
    return out

def filter_rows(rows: List[Dict[str,Any]], net=None, wit=None, branch=None, accounts=None, min_sat=None, max_sat=None):
    for r in rows:
        if net and r.get("network") != net: continue
        if wit and r.get("witness") != wit: continue
        if branch and r.get("branch") != branch: continue
        if accounts is not None:
            acc = r.get("account")
            if acc is None or int(acc) not in accounts: continue
        vs = r.get("value_sat")
        if min_sat is not None and isinstance(vs, int) and vs < min_sat: continue
        if max_sat is not None and isinstance(vs, int) and vs > max_sat: continue
        yield r

def mask_wif(w: Optional[str]) -> str:
    if not w: return ""
    return (w[:12]+"…") if len(w)>12 else w

def wsl_crlf_write(path: str, text: str):
    # CRLF для путей на Windows (WSL)
    nl = "\r\n" if path.startswith("/mnt/") else "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=nl) as f:
        f.write(text + nl)

def print_table(rows: List[Dict[str,Any]], wide=False, print_wif=False, limit=None):
    cols = ["ts","net","wit","acct","branch[idx]","addr","value_btc","txs","wif","wif_path"]
    print("\t".join(cols))
    n=0
    for r in rows:
        ts   = r.get("timestamp","")
        net  = r.get("network","")
        wit  = r.get("witness","")
        acct = r.get("account")
        acct = "" if acct is None else str(acct)
        bi   = f"{r.get('branch','')}[{r.get('index','')}]"
        addr = r.get("address","")
        valb = f"{sat_to_btc(r.get('value_sat',0)):.8f}"
        txs  = str(r.get("tx_count",""))
        wif  = r.get("wif")
        wp   = r.get("wif_path","") or ""
        if not print_wif: wif = "✓" if (wif or wp) else ""
        else: wif = mask_wif(wif)
        if not wide: wp = wp[:40]+"…" if len(wp)>41 else wp
        print("\t".join([ts,net,wit,acct,bi,addr,valb,txs,wif,wp]))
        n+=1
        if limit and n>=limit: break

def write_out(rows: List[Dict[str,Any]], out_csv=None, out_jsonl=None, limit=None):
    # экспорт отфильтрованных
    if out_csv:
        os.makedirs(os.path.dirname(out_csv), exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                i=0
                for r in rows:
                    w.writerow(r); i+=1
                    if limit and i>=limit: break
    if out_jsonl:
        os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
        with open(out_jsonl, "w", encoding="utf-8") as f:
            i=0
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n"); i+=1
                if limit and i>=limit: break

def heatmap_accounts(rows: List[Dict[str,Any]], width=60):
    acc_sum = {}
    for r in rows:
        a = r.get("account")
        if a is None: continue
        v = int(r.get("value_sat",0))
        acc_sum[a] = acc_sum.get(a,0)+v
    if not acc_sum:
        print("Нет данных по аккаунтам"); return
    maxv = max(acc_sum.values())
    for a in sorted(acc_sum.keys()):
        v = acc_sum[a]
        bar = int((v/maxv)*width) if maxv>0 else 0
        print(f"account {a:>3}: {v/1e8:,.8f} BTC | " + ("#"*bar))

def extract_wif(addr: str, keystore_path="keystore.jsonl", save_to=None, print_wif=False):
    if not os.path.isfile(keystore_path):
        raise FileNotFoundError(f"keystore не найден: {keystore_path}")
    wif=None; wif_path=None
    with open(keystore_path,"r",encoding="utf-8") as f:
        for line in f:
            try: rec=json.loads(line)
            except Exception: continue
            if rec.get("address")==addr:
                wif = rec.get("wif")
                wif_path = rec.get("wif_path")
                break
    if not wif and wif_path and os.path.isfile(wif_path):
        wif = open(wif_path,"r",encoding="utf-8").read().strip()
    if not wif:
        raise RuntimeError(f"WIF не найден для адреса: {addr}")
    if save_to:
        wsl_crlf_write(save_to, wif)
        print(color(f"✅ WIF сохранён в: {save_to}", "g"))
        try:
            import subprocess
            wpath = subprocess.check_output(["wslpath","-w",save_to], text=True).strip()
            subprocess.Popen(["powershell.exe","/c","notepad.exe",wpath])
        except Exception:
            pass
    if print_wif:
        print(wif)
    else:
        print(color("✓ WIF найден (скрыт, добавь --print-wif чтобы показать)", "y"))

def main():
    ap = argparse.ArgumentParser(description="Просмотр «хитов» сканера (JSONL) + WIF-экстрактор")
    ap.add_argument("--report", default="", help="Путь к отчёту JSONL или 'auto'")
    ap.add_argument("--network", default="")
    ap.add_argument("--witness", default="")
    ap.add_argument("--branch", choices=["receive","change",""], default="")
    ap.add_argument("--account", default="", help="Список аккаунтов: '0,1'")
    ap.add_argument("--min-sat", type=int, default=None)
    ap.add_argument("--max-sat", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-csv", default="")
    ap.add_argument("--out-jsonl", default="")
    ap.add_argument("--heatmap-accounts", action="store_true")
    ap.add_argument("--heatmap-width", type=int, default=60)
    ap.add_argument("--wide", action="store_true")
    ap.add_argument("--print-wif", action="store_true")
    ap.add_argument("--addr", default="", help="Режим извлечения WIF для конкретного адреса")
    ap.add_argument("--keystore", default="keystore.jsonl")
    ap.add_argument("--save-wif-to", default="", help="Куда сохранить WIF (например, /mnt/c/Users/roman/Desktop/wif.txt)")

    a = ap.parse_args()

    if a.addr:
        try:
            extract_wif(a.addr, keystore_path=a.keystore, save_to=(a.save_wif_to or None), print_wif=a.print_wif)
        except Exception as e:
            print(color(f"❌ {e}", "r"), file=sys.stderr); sys.exit(2)
        return

    rep = a.report
    if rep.strip().lower() == "auto" or not rep:
        rep = find_report_auto()
        if not rep:
            print(color("❌ Не найден отчёт. Укажи --report <path> или положи *.jsonl в ./scan_reports", "r"), file=sys.stderr)
            sys.exit(2)
        print(color(f"[auto] report: {rep}", "dim"))

    if not os.path.isfile(rep):
        print(color(f"❌ Файл отчёта не найден: {rep}", "r"), file=sys.stderr)
        sys.exit(2)

    try:
        rows = read_jsonl(rep)
    except Exception as e:
        print(color(f"❌ Не удалось прочитать {rep}: {e}", "r"), file=sys.stderr)
        sys.exit(2)

    accounts = parse_accounts(a.account)
    branch = a.branch or None
    net    = a.network or None
    wit    = a.witness or None

    filt = list(filter_rows(rows, net=net, wit=wit, branch=branch, accounts=accounts, min_sat=a.min_sat, max_sat=a.max_sat))

    if a.heatmap_accounts:
        heatmap_accounts(filt, width=a.heatmap_width)
        return

    print_table(filt, wide=a.wide, print_wif=a.print_wif, limit=a.limit)
    if a.out_csv or a.out_jsonl:
        write_out(filt, out_csv=(a.out_csv or None), out_jsonl=(a.out_jsonl or None), limit=a.limit)
        print(color("OK: экспорт сохранён", "g"))

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(130)
