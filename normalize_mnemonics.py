import sys, re
from mnemonic import Mnemonic

mn = Mnemonic("english")
def explode(s: str):
    s = s.replace("\r","")
    for d in [",",";","|","\t"]:
        s = s.replace(d,"\n")
    return [x for x in s.splitlines()]

def clean(s: str):
    s = s.lower().replace("\u200b","").strip()
    s = s.strip("\"'`")
    s = re.sub(r"\s+", " ", s)
    return s

src = sys.argv[1] if len(sys.argv)>1 else "mnemonics.txt"
seen=set(); ok=[]
with open(src,encoding="utf-8") as f:
    for raw in f:
        for chunk in explode(raw):
            p = clean(chunk)
            if not p or p.startswith("#"): continue
            if p in seen: continue
            seen.add(p)
            if mn.check(p):
                ok.append(p)
print("\n".join(ok))
print(f"\n# VALID_COUNT {len(ok)}", file=sys.stderr)
