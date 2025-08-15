from bitcoinlib.wallets import Wallet
from bitcoinlib.services.services import ServiceError

# Список кошельков, с которыми работаем
WALLET_NAMES = [
    "demo_wallet",
    "wallet_test_1",
    "wallet_test_2"
]

for name in WALLET_NAMES:
    print(f"\n=== {name} ===")
    try:
        w = Wallet(name)  # пробуем открыть
        print("[OK] Открыт существующий кошелёк:", w.name)
    except Exception:
        try:
            w = Wallet.create(
                name,
                network='bitcoin',      # или 'testnet'
                witness_type='segwit',  # 'legacy', 'segwit', 'p2sh-segwit', 'taproot'
                keys=1,
                db_uri=None
            )
            print("[OK] Создан новый кошелёк:", w.name)
        except Exception as e:
            print("[ERR] Не удалось создать кошелёк:", e)
            continue

    # Печатаем первый адрес
    try:
        addr = w.get_key().address
        print("[ADDR]", addr)
    except Exception as e:
        print("[WARN] Не удалось получить адрес:", e)

    # Сканируем баланс
    try:
        print("[*] Сканирую...")
        w.scan()
        bal = w.get_balance()
        print("[OK] Баланс (BTC):", bal)
    except ServiceError as e:
        print("[WARN] Сервис недоступен:", e)
    except Exception as e:
        print("[WARN] Ошибка при сканировании:", e)
