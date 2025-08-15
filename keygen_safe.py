#!/usr/bin/env python3
import os, json, secrets, stat
from datetime import datetime
from bip_utils import WifEncoder

# порядок секрета secp256k1
N = int("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def gen_priv32():
    while True:
        b = secrets.token_bytes(32)
        x = int.from_bytes(b, "big")
        if 1 <= x < N:
            return b

def ensure_dir(p): os.makedirs(p, exist_ok=True); return p
def ts(): return datetime.now().strftime("%Y%m%d_%H%M%S")

def main():
    priv = gen_priv32()
    wif_main = WifEncoder.Encode(priv, compr_pub_key=True, net_ver=0x80)  # mainnet
    wif_test = WifEncoder.Encode(priv, compr_pub_key=True, net_ver=0xEF)  # testnet

    out_dir = ensure_dir("./secrets")
    stamp = ts()
    json_path = os.path.join(out_dir, f"privkey-{stamp}.json")
    md_path   = os.path.join(out_dir, f"PRIVKEY-{stamp}.md")

    data = {
        "created_at": datetime.utcnow().isoformat()+"Z",
        "priv_hex": priv.hex(),
        "wif_mainnet": wif_main,
        "wif_testnet": wif_test,
        "note": "Храни оффлайн. НЕ коммить в git. Сделай оффлайн-бэкап."
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Private key passport\n\n")
        f.write(f"- Created: {data['created_at']}\n")
        f.write(f"- priv_hex: {data['priv_hex']}\n")
        f.write(f"- WIF (mainnet): {data['wif_mainnet']}\n")
        f.write(f"- WIF (testnet): {data['wif_testnet']}\n")
        f.write("\n**ВНИМАНИЕ:** хранить оффлайн, не отправлять в сеть, не коммитить в репозиторий.\n")

    # Права 600
    for p in (json_path, md_path):
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)

    print(f"[OK] Сохранено:\n  {json_path}\n  {md_path}\n(ключ в консоль не выводится)")

if __name__ == "__main__":
    main()
