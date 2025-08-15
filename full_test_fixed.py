from bitcoinlib.keys import Key
from bitcoinlib.wallets import Wallet
import requests

print("=== 1. Тест библиотеки bitcoinlib ===")
k = Key()
print("Адрес (P2PKH):", k.address())
print("WIF:", k.wif())
print()

print("=== 2. Создание/открытие SegWit-кошелька ===")
WALLET_NAME = "demo_wallet"
try:
    w = Wallet(WALLET_NAME)
    print("Открыт существующий кошелёк:", w.name)
except Exception:
    w = Wallet.create(WALLET_NAME, network='bitcoin', witness_type='segwit', keys=1)
    print("Создан новый кошелёк:", w.name)
print()

print("=== 3A. Первые 5 адресов (простой способ: next key) ===")
addrs_a = []
for i in range(5):
    key = w.get_key(change=0)          # берём следующий приёмный ключ
    addrs_a.append(key.address)
    print(f"{i+1}: {key.address}")

print("\n=== 3B. Те же индексы через путь деривации (точный способ) ===")
# m/84'/0'/0'/0/i — приёмные адреса для mainnet SegWit (BIP84)
addrs_b = []
for i in range(5):
    key = w.get_key(path=f"m/84'/0'/0'/0/{i}")
    addrs_b.append(key.address)
    print(f"i={i}: {key.address}")

print("\n=== 4. Проверка баланса первого адреса (Blockstream API) ===")
addr = addrs_b[0] if addrs_b else addrs_a[0]
try:
    r = requests.get(f"https://blockstream.info/api/address/{addr}", timeout=10)
    r.raise_for_status()
    data = r.json()
    cs = data.get("chain_stats", {})
    ms = data.get("mempool_stats", {})
    confirmed = cs.get("funded_txo_sum", 0) - cs.get("spent_txo_sum", 0)
    unconfirmed = ms.get("funded_txo_sum", 0) - ms.get("spent_txo_sum", 0)
    print("Адрес:", addr)
    print("Баланс подтверждённый (сатоши):", confirmed)
    print("Баланс неподтверждённый (сатоши):", unconfirmed)
    print("Баланс общий (сатоши):", confirmed + unconfirmed)
except Exception as e:
    print("Ошибка при получении баланса:", e)

print("\n=== Тест завершён ===")
