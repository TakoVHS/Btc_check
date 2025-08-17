# Bitcoin Wallet Tools - Configuration Templates

## Конфигурационные файлы для различных сценариев

### 1. batch_config_testnet.json - Тестирование на testnet
```json
{
  "description": "Тестовая конфигурация для testnet",
  "jobs": [
    {
      "type": "gen",
      "name": "testnet_segwit_basic",
      "wallet": "test_wallet",
      "network": "testnet", 
      "witness": "segwit",
      "accounts": [0, 1],
      "start": 0,
      "count": 20,
      "out_dir": "./test_exports",
      "format": "csv,jsonl"
    },
    {
      "type": "gen", 
      "name": "testnet_taproot",
      "wallet": "test_tr",
      "network": "testnet",
      "witness": "tr", 
      "accounts": [0],
      "start": 0,
      "count": 10,
      "out_dir": "./test_exports"
    }
  ]
}
```

### 2. batch_config_production.json - Продуктивная работа  
```json
{
  "description": "Продуктивная конфигурация для mainnet",
  "jobs": [
    {
      "type": "gen",
      "name": "bitcoin_legacy",
      "wallet": "btc_legacy",
      "network": "bitcoin",
      "witness": "legacy",
      "accounts": [0, 1, 2],
      "start": 0, 
      "count": 100,
      "out_dir": "./prod_exports",
      "format": "jsonl"
    },
    {
      "type": "gen",
      "name": "bitcoin_segwit",
      "wallet": "btc_segwit", 
      "network": "bitcoin",
      "witness": "segwit",
      "accounts": [0, 1, 2, 3, 4],
      "start": 0,
      "count": 200,
      "out_dir": "./prod_exports"
    },
    {
      "type": "gen",
      "name": "bitcoin_taproot",
      "wallet": "btc_taproot",
      "network": "bitcoin", 
      "witness": "tr",
      "accounts": [0, 1],
      "start": 0,
      "count": 50,
      "out_dir": "./prod_exports"
    }
  ]
}
```

### 3. scan_config.json - Конфигурация сканирования
```json
{
  "scan_settings": {
    "backend": "blockstream",
    "workers": 4,
    "delay_ms": 150,
    "confirmed_only": false,
    "timeout_seconds": 30
  },
  "networks": {
    "bitcoin": {
      "api_base": "https://blockstream.info/api",
      "delay_ms": 200
    },
    "testnet": {
      "api_base": "https://blockstream.info/testnet/api", 
      "delay_ms": 100
    }
  },
  "security": {
    "write_keys_on_hit": false,
    "hits_dir": "./hits",
    "require_confirmation": true
  }
}
```

### 4. matrix_configs.txt - Примеры матриц для массовой генерации

#### Полная матрица для Bitcoin
```
bitcoin:legacy,bitcoin:p2sh,bitcoin:segwit,bitcoin:tr
```

#### Только современные форматы
```
bitcoin:segwit,bitcoin:tr
```

#### Тестирование на всех сетях
```
bitcoin:segwit,testnet:segwit,regtest:segwit
```

#### Комплексная матрица
```
bitcoin:legacy,bitcoin:p2sh,bitcoin:segwit,bitcoin:tr,testnet:legacy,testnet:segwit,testnet:tr
```

### 5. security_config.json - Настройки безопасности
```json
{
  "security": {
    "auto_print_privates": false,
    "require_explicit_confirmation": true,
    "secure_directories": [
      "./secure",
      "./hits", 
      "./private_keys"
    ],
    "file_permissions": {
      "mnemonic_files": "600",
      "private_key_files": "600",
      "secure_directories": "700"
    }
  },
  "backup": {
    "auto_backup": true,
    "backup_dir": "./backups",
    "retention_days": 30,
    "exclude_patterns": ["*.log", "*.tmp"]
  }
}
```

### 6. windows_paths.json - Пути для WSL интеграции
```json
{
  "windows_integration": {
    "desktop_path": "/mnt/c/Users/{username}/Desktop",
    "downloads_path": "/mnt/c/Users/{username}/Downloads", 
    "documents_path": "/mnt/c/Users/{username}/Documents",
    "results_dir": "/mnt/c/Users/{username}/Desktop/btc_results"
  },
  "wsl_paths": {
    "project_root": "/home/{username}/btc_tools/Btc_check",
    "exports": "./exports",
    "secure": "./secure", 
    "logs": "./logs"
  }
}
```

### 7. performance_config.json - Настройки производительности
```json
{
  "performance": {
    "max_workers": 4,
    "chunk_size": 1000,
    "memory_limit_mb": 512,
    "timeout_seconds": 300
  },
  "api_limits": {
    "blockstream_delay_ms": 150,
    "max_retries": 3,
    "backoff_factor": 2.0
  },
  "optimization": {
    "cache_xpubs": true,
    "batch_requests": true,
    "parallel_derivation": true
  }
}
```

### 8. Переменные окружения (.env)
```bash
# Bitcoin Tools Environment Configuration

# Основные настройки
BTC_DEFAULT_NETWORK=testnet
BTC_DEFAULT_WITNESS=segwit
BTC_WORKERS=4
BTC_DELAY_MS=150

# Пути
BTC_EXPORTS_DIR=./exports
BTC_SECURE_DIR=./secure
BTC_HITS_DIR=./hits
BTC_LOGS_DIR=./logs

# Windows интеграция (WSL)
WINDOWS_USER=YourUsername
WINDOWS_DESKTOP=/mnt/c/Users/$WINDOWS_USER/Desktop
BTC_RESULTS_DIR=$WINDOWS_DESKTOP/btc_results

# Безопасность
BTC_AUTO_BACKUP=true
BTC_REQUIRE_CONFIRMATION=true
BTC_SECURE_PERMS=600

# API настройки
BLOCKSTREAM_API_DELAY=150
BLOCKSTREAM_MAX_RETRIES=3
BLOCKSTREAM_TIMEOUT=30
```

## Использование конфигураций

### Запуск с конфигурацией
```bash
# Пакетная обработка с конфигом
python3 batch_wallets.py --config batch_config_testnet.json

# Массовая генерация с матрицей
python3 mass_wallet_tool.py gen-batch --matrix "bitcoin:segwit,testnet:tr"

# Загрузка переменных окружения
source .env
```

### Создание собственной конфигурации
```bash
# Копирование шаблона
cp batch_config_testnet.json my_config.json

# Редактирование
nano my_config.json

# Запуск
python3 batch_wallets.py --config my_config.json
```