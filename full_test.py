from bitcoinlib.keys import Key
from bitcoinlib.wallets import Wallet
import requests

print("=== 1. Тест библиотеки bitcoinlib ===")
k = Key()
print("Адрес (P2PKH):", k.address())
print("WIF:", k.wif())
print()

print("=== 2. Создание/открытие SegWit кошелька ===")
WALLET_NAME = "demo_wallet"
try:
    w = Wallet(WALLET_NAME)
    print("Открыт существующий кошелёк:", w.name)
except:
    w = Wallet.create(WALLET_NAME, network='bitcoin', witness_type='segwit', keys=1)
    print("Создан новый кошелёк:", w.name)

print()

print("=== 3. Первые 5 SegWit-адресов ===")
addresses = []
for i in range(5):
    key = w.get_key(change=0, index=i)
    addresses.append(key.address)
    print(f"{i+1}: {key.address}")

print()

print("=== 4. Проверка баланса первого адреса через Blockstream API ===")
addr = addresses[0]
try:
    r = requests.get(f"https://blockstream.info/api/address/{addr}", timeout=10)
    r.raise_for_status()
    data = r.json()
    chain_stats = data.get("chain_stats", {})
    mempool_stats = data.get("mempool_stats", {})
    confirmed = chain_stats.get("funded_txo_sum", 0) - chain_stats.get("spent_txo_sum", 0)
    unconfirmed = mempool_stats.get("funded_txo_sum", 0) - mempool_stats.get("spent_txo_sum", 0)
    print("Адрес:", addr)
    print("Баланс подтверждённый (сатоши):", confirmed)
    print("Баланс неподтверждённый (сатоши):", unconfirmed)
    print("Баланс общий (сатоши):", confirmed + unconfirmed)
except Exception as e:
    print("Ошибка при получении баланса:", e)

print("\n=== Тест завершён ===")
