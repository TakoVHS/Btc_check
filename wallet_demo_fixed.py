from bitcoinlib.wallets import Wallet
from bitcoinlib.services.services import ServiceError

WALLET_NAME = 'demo_wallet'

# Открываем или создаём, если нет
try:
    w = Wallet(WALLET_NAME)
    print("Открыт существующий кошелёк:", w.name)
except Exception:
    w = Wallet.create(WALLET_NAME, network='bitcoin', witness_type='segwit', keys=1)
    print("Создан новый кошелёк:", w.name)

k = w.get_key()  # текущий приёмный адрес
print("Address:", k.address)

# Безопасная синхронизация + баланс
try:
    w.scan()
except ServiceError as e:
    print("Scan service error:", e)
except Exception as e:
    print("Scan error:", e)

try:
    # Надёжнее так:
    bal = w.get_balance()         # Decimal в BTC
    print("Balance (BTC):", bal)
except Exception as e:
    print("Balance unavailable:", e)
