# Bitcoin Wallet Tools 🚀

Комплект инструментов для работы с Bitcoin кошельками на WSL/Linux

## 🎯 Два основных проекта

### 1. **mass_wallet_tool.py** - Массовая генерация и сканирование
**Самый мощный инструмент для массовой работы с кошельками**

**Возможности:**
- ✅ Массовая генерация адресов по матрице (сети × типы свидетельств)
- ✅ Поддержка BIP44/49/84/86 (Legacy, P2SH, Segwit, Taproot)
- ✅ Пакетное сканирование балансов через Blockstream API
- ✅ Безопасное сохранение приватных ключей (только по явному запросу)
- ✅ Автоматическое сохранение WIF при обнаружении балансов
- ✅ Многопоточное сканирование с настраиваемой задержкой

**Основные команды:**
```bash
# Генерация по матрице сетей и типов
python3 mass_wallet_tool.py gen-batch \
  --matrix "bitcoin:segwit,testnet:tr,bitcoin:legacy" \
  --accounts "0-4" \
  --count 1000 \
  --include-priv

# Сканирование балансов  
python3 mass_wallet_tool.py scan \
  --src-jsonl addresses_*.jsonl \
  --out-report scan_results.jsonl \
  --write-keys-on-hit \
  --i-understand
```

### 2. **wallet_tool.py** - Точная индивидуальная работа
**Профессиональный инструмент для работы с отдельными кошельками**

**Возможности:**
- ✅ Генерация адресов из мнемоники/xpub
- ✅ Поддержка Descriptor/Miniscript через embit
- ✅ Верификация адресов и путей деривации
- ✅ Экспорт в CSV/JSONL с временными метками
- ✅ Интеграция с bitcoinlib для максимальной совместимости

**Основные команды:**
```bash
# Генерация из мнемоники
python3 wallet_tool.py gen \
  --mnemonic "ваша мнемоника из 12 слов" \
  --network bitcoin \
  --witness segwit \
  --count 100

# Верификация адресов
python3 wallet_tool.py verify \
  --xpub "xpub..." \
  --compare-file addresses.csv
```

## 🚀 Быстрая установка на WSL

### Автоматическая установка (рекомендуется)
```bash
# Клонирование и запуск установщика
git clone https://github.com/TakoVHS/Btc_check.git
cd Btc_check
./setup_wsl.sh
```

### Ручная установка
```bash
# Подготовка системы
sudo apt update && sudo apt install -y python3 python3-pip python3-venv build-essential

# Установка зависимостей
pip3 install bip-utils bitcoinlib requests embit mnemonic pandas

# Настройка окружения
python3 -m venv btc_env
source btc_env/bin/activate
```

## 📖 Быстрый старт

### 1. Тестирование (безопасно на testnet)
```bash
# Активация окружения
source btc_env/bin/activate

# Генерация 5 тестовых адресов
python3 wallet_tool.py gen --network testnet --witness segwit --count 5

# Массовая генерация для тестирования
python3 mass_wallet_tool.py gen-batch \
  --matrix "testnet:segwit,testnet:tr" \
  --accounts "0-1" \
  --count 50 \
  --out-dir ./test_exports
```

### 2. Продуктивная работа (mainnet)
```bash
# Осторожно! Только после тестирования!
python3 mass_wallet_tool.py gen-batch \
  --matrix "bitcoin:legacy,bitcoin:segwit,bitcoin:tr" \
  --accounts "0-9" \
  --count 10000 \
  --include-priv \
  --save-mnemonic ./secure/master_mnemonic.txt
```

## 🛠️ Дополнительные инструменты

### show_hits.py - Анализ результатов
```bash
# Просмотр найденных адресов с балансами
python3 show_hits.py --report auto --min-sat 1

# Извлечение WIF ключа
python3 show_hits.py --addr "адрес" --print-wif --save-wif-to /mnt/c/Users/user/Desktop/key.txt
```

### batch_wallets.py - Пакетная обработка
```bash
# Запуск множественных заданий
python3 batch_wallets.py --config batch_config_testnet.json --max-workers 4
```

## 🔒 Безопасность

### Защита приватных данных
- 🔐 Папка `secure/` с правами доступа 700
- 🔐 Автоматическое исключение приватных файлов из git  
- 🔐 Приватные ключи никогда не выводятся без явного флага
- 🔐 Обязательное подтверждение для операций с рисками

### Рекомендации
```bash
# Создание защищенной директории
mkdir -p secure && chmod 700 secure

# Сохранение мнемоники
echo "ваша мнемоника" > secure/mnemonic.txt && chmod 600 secure/mnemonic.txt

# Резервное копирование (исключая логи)
tar -czf backup_$(date +%Y%m%d).tar.gz exports/ secure/ --exclude='*.log'
```

## 🎯 Практические сценарии

### Сценарий 1: Исследование старых кошельков
```bash
# Генерация адресов с известной мнемоникой
python3 wallet_tool.py gen \
  --mnemonic "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about" \
  --matrix "bitcoin:legacy,bitcoin:segwit" \
  --accounts "0-19" \
  --count 1000

# Сканирование балансов
python3 mass_wallet_tool.py scan \
  --src-jsonl addresses_*.jsonl \
  --out-report results.jsonl \
  --workers 2 \
  --delay-ms 200
```

### Сценарий 2: Анализ различных путей деривации
```bash
# Генерация для множественных аккаунтов
python3 mass_wallet_tool.py gen-batch \
  --matrix "bitcoin:segwit" \
  --accounts "0-49" \
  --start 0 \
  --count 200 \
  --include-priv
```

### Сценарий 3: Поиск потерянных средств  
```bash
# Осторожная проверка с сохранением ключей при находках
python3 mass_wallet_tool.py scan \
  --src-jsonl known_addresses.jsonl \
  --keystore-json keystore.json \
  --write-keys-on-hit \
  --hits-dir ./hits \
  --i-understand
```

## 📁 Структура файлов

```
Btc_check/
├── wallet_tool.py          # Основной инструмент генерации
├── mass_wallet_tool.py     # Массовая обработка  
├── batch_wallets.py        # Пакетная обработка
├── show_hits.py           # Анализ результатов
├── setup_wsl.sh           # Автоустановщик для WSL
├── quick_examples.sh      # Примеры использования
├── CONFIG_TEMPLATES.md    # Шаблоны конфигураций
├── WSL_SETUP_GUIDE.md    # Подробное руководство
├── secure/               # Защищенная папка для приватных данных
├── exports/              # Результаты генерации
├── hits/                 # Найденные адреса с балансами
└── mass_exports/         # Результаты массовой генерации
```

## 🤝 Поддержка

### Получение справки
```bash
python3 wallet_tool.py --help
python3 mass_wallet_tool.py --help  
python3 show_hits.py --help
```

### Проверка установки
```bash
# Тест импорта модулей
python3 -c "import bip_utils, bitcoinlib, requests; print('✅ Все зависимости OK')"

# Быстрый тест генерации
python3 wallet_tool.py gen --network testnet --count 3
```

### Примеры использования
```bash
# Запуск файла с примерами
./quick_examples.sh
```

## ⚠️ Важные предупреждения

1. **Тестирование**: Всегда начинайте с testnet
2. **Безопасность**: Храните мнемоники в `secure/` 
3. **Резервные копии**: Делайте бэкапы важных данных
4. **Проверка**: Верифицируйте адреса перед использованием
5. **Осознанность**: Используйте `--i-understand` только понимая риски

## 🎉 Готово к работе!

После установки используйте алиасы для быстрого доступа:
- `btc-activate` - активация окружения
- `btc-gen --help` - справка по генерации
- `btc-mass --help` - справка по массовой обработке  
- `btc-hits --help` - справка по анализу результатов

**Начните с:** `python3 wallet_tool.py gen --network testnet --count 5`