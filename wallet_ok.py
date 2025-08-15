from bitcoinlib.wallets import Wallet
from bitcoinlib.services.services import ServiceError

WALLET_NAME = 'demo_wallet'

# Открыть или создать (в try/except)
try:
    w = Wallet(WALLET_NAME)
    print("Открыт существующий кошелёк:", w.name)
except Exception:
    w = Wallet.create(WALLET_NAME, network='bitcoin', witness_type='segwit', keys=1)
    print("Создан новый кошелёк:", w.name)

print("\n=== Адреса (receive) ===")
# В ЭТОЙ версии get_key() возвращает текущий ключ.
# Чтобы получить N УНИКАЛЬНЫХ адресов, используем new_key(change=0).
addrs = []
for i in range(5):
    k = w.new_key(change=0)     # получить следующий приёмный адрес и сохранить его в БД кошелька
    addrs.append(k.address)
    print(f"{i}: {k.address}")

print("\n=== Скан и баланс ===")
try:
    w.scan()
    print("Сканирование завершено")
except ServiceError as e:
    print("Service error:", e)
except Exception as e:
    print("Scan error:", e)

try:
    # В ТВОЕЙ версии bitcoinlib — balance(), не get_balance()
    bal = w.balance()    # Decimal в BTC
    print("Balance (BTC):", bal)
except Exception as e:
    print("Balance unavailable:", e)
