# WSL Installation Guide / Руководство по установке на WSL

## Быстрая установка (Quick Setup)

### 1. Подготовка WSL системы
```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и необходимых инструментов
sudo apt install -y python3 python3-pip python3-venv git curl wget

# Установка build-essentials для компиляции некоторых пакетов
sudo apt install -y build-essential libffi-dev libssl-dev
```

### 2. Клонирование репозитория
```bash
# Клонирование проекта
git clone https://github.com/TakoVHS/Btc_check.git
cd Btc_check

# Создание виртуального окружения
python3 -m venv btc_env
source btc_env/bin/activate
```

### 3. Установка зависимостей
```bash
# Обновление pip
pip install --upgrade pip

# Установка основных зависимостей
pip install bip-utils==2.9.3 bitcoinlib==0.7.5 requests embit mnemonic

# Установка дополнительных зависимостей
pip install pandas openpyxl aiohttp
```

## Главные инструменты

### 🔧 mass_wallet_tool.py - Массовая обработка

#### Генерация массива адресов:
```bash
python3 mass_wallet_tool.py gen-batch \
  --matrix "bitcoin:legacy,bitcoin:segwit,testnet:tr" \
  --accounts "0-2" \
  --start 0 \
  --count 100 \
  --out-dir ./mass_exports \
  --include-priv \
  --save-mnemonic ./secure/mnemonic.txt
```

#### Сканирование балансов:
```bash
python3 mass_wallet_tool.py scan \
  --src-jsonl ./mass_exports/addresses_*.jsonl \
  --out-report ./scan_results.jsonl \
  --workers 4 \
  --delay-ms 150 \
  --keystore-json ./mass_exports/keystore.json \
  --write-keys-on-hit \
  --hits-dir ./hits \
  --i-understand
```

### 🔧 wallet_tool.py - Индивидуальная работа

#### Генерация из мнемоники:
```bash
python3 wallet_tool.py gen \
  --mnemonic "your twelve word mnemonic phrase here example test" \
  --network bitcoin \
  --witness segwit \
  --account 0 \
  --count 20 \
  --out-dir ./exports
```

#### Верификация адресов:
```bash
python3 wallet_tool.py verify \
  --xpub "xpub..." \
  --network bitcoin \
  --witness segwit \
  --start 0 \
  --count 10 \
  --compare-file ./exports/addresses_*.csv
```

## Безопасность

### 🔒 Настройка безопасных директорий
```bash
# Создание защищенных папок
mkdir -p secure hits exports mass_exports
chmod 700 secure hits

# Настройка .gitignore для приватных данных
echo "secure/" >> .gitignore
echo "hits/" >> .gitignore
echo "*.mnemonic" >> .gitignore
echo "*private*" >> .gitignore
```

### 🔐 Работа с приватными ключами
```bash
# Извлечение WIF ключа для найденного адреса
python3 show_hits.py \
  --addr "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2" \
  --keystore keystore.jsonl \
  --save-wif-to /mnt/c/Users/yourusername/Desktop/found_key.txt \
  --print-wif
```

## Оптимизация для WSL

### Настройка путей Windows
```bash
# Пример сохранения результатов на диск Windows
export WINDOWS_DESKTOP="/mnt/c/Users/$USER/Desktop"
export RESULTS_DIR="$WINDOWS_DESKTOP/btc_results"
mkdir -p "$RESULTS_DIR"
```

### Алиасы для удобства
```bash
# Добавить в ~/.bashrc
echo 'alias btc-gen="python3 /path/to/Btc_check/wallet_tool.py"' >> ~/.bashrc
echo 'alias btc-mass="python3 /path/to/Btc_check/mass_wallet_tool.py"' >> ~/.bashrc
echo 'alias btc-hits="python3 /path/to/Btc_check/show_hits.py"' >> ~/.bashrc
source ~/.bashrc
```

## Примеры использования

### Быстрый тест генерации
```bash
# Тестовая генерация для testnet
python3 wallet_tool.py gen \
  --network testnet \
  --witness segwit \
  --account 0 \
  --count 5 \
  --out-dir ./test_exports
```

### Пакетная обработка
```bash
# Создание множественных кошельков
python3 batch_wallets.py \
  --config batch_jobs.json \
  --max-workers 4 \
  --exports-dir ./batch_results
```

## Устранение проблем

### Проблемы с зависимостями
```bash
# Переустановка проблемных пакетов
pip uninstall bitcoinlib bip-utils
pip install --no-cache-dir bitcoinlib==0.7.5 bip-utils==2.9.3
```

### Права доступа
```bash
# Исправление прав доступа
find . -name "*.py" -exec chmod +x {} \;
chmod 600 secure/*
```

### Проверка установки
```bash
# Тест основных компонентов
python3 -c "import bip_utils, bitcoinlib, requests; print('All dependencies OK')"
```

## Полезные команды

```bash
# Активация окружения (всегда перед работой)
source btc_env/bin/activate

# Просмотр найденных адресов с балансами
python3 show_hits.py --report auto --min-sat 1

# Создание резервной копии результатов
tar -czf backup_$(date +%Y%m%d).tar.gz exports/ mass_exports/ hits/
```

## Конфигурационные файлы

Создайте файл `config.json` для часто используемых настроек:
```json
{
  "default_network": "bitcoin",
  "default_witness": "segwit", 
  "workers": 4,
  "delay_ms": 150,
  "export_dir": "./exports"
}
```