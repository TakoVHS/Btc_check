from bitcoinlib.wallets import Wallet

# создаст локальную БД ~/.bitcoinlib и кошелёк, если его ещё нет
w = Wallet.create('demo_wallet', network='bitcoin', witness_type='segwit', db_uri=None, keys=1)

k = w.get_key()              # получить ключ
print("Wallet:", w.name)
print("Address:", k.address) # адрес для приёма BTC

# Обновить UTXO/баланс (потребует интернет и может занять время)
try:
    w.scan()                 # синхронизация с сетевыми сервисами
    info = w.info()
    print("Balance (satoshi):", info.get('balance'))
except Exception as e:
    print("Scan skipped or failed:", e)
