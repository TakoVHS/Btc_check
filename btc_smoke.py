from bitcoinlib.keys import Key

k = Key()  # сгенерировать новый ключ
print("OK. Address:", k.address())
