#!/usr/bin/env python3
import os, sys, csv, json
from typing import Iterable, Any, List, Tuple
from collections import OrderedDict
try:
    import openpyxl
except Exception:
    openpyxl = None
from mnemonic import Mnemonic

MN = Mnemonic("english")
BIP_WORDS = set(MN.wordlist)
VALID_WC = {12,15,18,21,24}

def _norm(s:str)->str: return " ".join(s.strip().lower().split())

def is_mnemonic_like(s: str) -> bool:
    t = _norm(s)
    if not t: return False
    w = t.split()
    return len(w) in VALID_WC and all(x in BIP_WORDS for x in w)

def walk_json(x: Any) -> Iterable[str]:
    if isinstance(x, dict):
        for v in x.values(): yield from walk_json(v)
    elif isinstance(x, list):
        for v in x: yield from walk_json(v)
    elif isinstance(x, str):
        yield x

def read_txt(path: str) -> Iterable[str]:
    with open(path, encoding="utf-8") as f:
        for ln in f: yield ln.rstrip("\n")

def read_csv_generic(path: str) -> Iterable[str]:
    with open(path, encoding="utf-8") as f:
        head = f.read(4096); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(head, delimiters=",;|\t")
        except Exception:
            dialect = csv.excel
        for row in csv.reader(f, dialect):
            for cell in row:
                if cell: yield cell

def read_xlsx(path: str) -> Iterable[str]:
    if openpyxl is None: return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str) and cell.strip():
                    yield cell

def read_json(path: str) -> Iterable[str]:
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
            yield from walk_json(data)
        except json.JSONDecodeError:
            f.seek(0)
            for ln in f:
                ln = ln.strip()
                if not ln: continue
                try:
                    obj = json.loads(ln)
                    yield from walk_json(obj)
                except Exception:
                    yield ln

def harvest_candidates(path: str) -> Iterable[str]:
    ext = os.path.splitext(path.lower())[1]
    if ext in (".txt",""):         yield from read_txt(path)
    elif ext in (".json",".oxp",".xps"): yield from read_json(path)
    elif ext in (".csv",):         yield from read_csv_generic(path)
    elif ext in (".xlsx",".xls"):  yield from read_xlsx(path)
    else:                          yield from read_txt(path)

def normalize_and_validate(cands: Iterable[str]) -> Tuple[List[str], List[Tuple[str,str]]]:
    ok, bad = [], []
    for s in cands:
        t = _norm(s)
        if not t: continue
        w = t.split()
        if len(w) not in VALID_WC:
            bad.append((s, f"word_count={len(w)}")); continue
        if not all(x in BIP_WORDS for x in w):
            bad.append((s, "not_in_bip39")); continue
        if not MN.check(t):
            bad.append((s, "checksum_fail")); continue
        ok.append(t)
    uniq = list(OrderedDict.fromkeys(ok))
    return uniq, bad

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Конвертер OXP/JSON/CSV/XLSX/TXT → mnemonics.txt")
    ap.add_argument("-i","--input", required=True, help="исходный файл")
    ap.add_argument("-o","--out", default="mnemonics.txt", help="куда писать валидные сид-фразы")
    ap.add_argument("-b","--bad", default="mnemonics_bad.csv", help="куда писать отбраковку")
    args = ap.parse_args()

    cands = list(harvest_candidates(args.input))
    good, bad = normalize_and_validate(cands)

    with open(args.out,"w",encoding="utf-8") as g:
        for s in good: g.write(s+"\n")
    with open(args.bad,"w",newline="",encoding="utf-8") as g:
        w = csv.writer(g); w.writerow(["raw","reason"]); w.writerows(bad)

    print(f"[OK] {args.out}: {len(good)} валидных | rejected: {len(bad)} -> {args.bad}")

if __name__=="__main__":
    main()
