import csv
OUT="nonzero_report.csv"
header=["wallet_id","idx","preview","network","profile","address_index","address","confirmed_sats","unconfirmed_sats","total_sats"]

# загрузим lookup
L={}
with open("mnemonic_lookup.csv",encoding="utf-8") as f:
    for r in csv.DictReader(f):
        L[r["wallet_id"]]=r

rows=[header]
for fn in ("addresses_with_balance_bitcoin.csv","addresses_with_balance_testnet.csv"):
    try:
        with open(fn,encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if int(r["total_sats"])>0:
                    m=L.get(r["wallet_id"],{})
                    rows.append([
                        r["wallet_id"], m.get("idx",""), m.get("preview",""),
                        r["network"], r["profile"], r["address_index"], r["address"],
                        r["confirmed_sats"], r["unconfirmed_sats"], r["total_sats"]
                    ])
    except FileNotFoundError:
        pass

with open(OUT,"w",newline="",encoding="utf-8") as f:
    csv.writer(f).writerows(rows)
print("[OK] wrote", OUT, "rows:", len(rows)-1)
