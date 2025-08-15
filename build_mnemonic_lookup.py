import csv, hashlib
from mnemonic import Mnemonic

MN_FILE = "mnemonics.txt"
OUT     = "mnemonic_lookup.csv"
REVEAL_FULL_PHRASE = False  # ради безопасности по умолчанию скрываем полную фразу

mn = Mnemonic("english")
rows = [["wallet_id","idx","word_count","preview","phrase_if_enabled"]]

with open(MN_FILE, "r", encoding="utf-8") as f:
    idx = 0
    for i, ln in enumerate(f, 1):
        s = " ".join(ln.split())
        if not s or s.lstrip().startswith("#"):
            continue
        idx += 1
        if not mn.check(s):
            continue
        wid = hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]
        words = s.split()
        preview = " ".join(words[:2]) + " … " + " ".join(words[-2:])
        rows.append([wid, idx, len(words), preview, s if REVEAL_FULL_PHRASE else ""])

with open(OUT, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(rows)

print(f"[OK] wrote {OUT}, records: {len(rows)-1}")
