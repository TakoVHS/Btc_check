#!/bin/bash
# setup_wsl.sh - Автоматическая установка Bitcoin Wallet Tools на WSL

set -e

echo "🚀 Bitcoin Wallet Tools - WSL Setup"
echo "==================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка WSL
if [[ ! -f /proc/version ]] || ! grep -q "Microsoft\|WSL" /proc/version 2>/dev/null; then
    print_warning "Обнаружена не WSL система. Скрипт оптимизирован для WSL."
fi

# Обновление системы
print_status "Обновление системы..."
sudo apt update && sudo apt upgrade -y

# Установка системных зависимостей
print_status "Установка системных зависимостей..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    curl \
    wget \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    libsecp256k1-dev

# Создание рабочей директории
WORK_DIR="$HOME/btc_tools"
if [[ ! -d "$WORK_DIR" ]]; then
    print_status "Создание рабочей директории: $WORK_DIR"
    mkdir -p "$WORK_DIR"
fi

cd "$WORK_DIR"

# Клонирование репозитория (если еще не склонирован)
if [[ ! -d "Btc_check" ]]; then
    print_status "Клонирование репозитория..."
    git clone https://github.com/TakoVHS/Btc_check.git
fi

cd Btc_check

# Создание виртуального окружения
print_status "Создание виртуального окружения..."
if [[ ! -d "btc_env" ]]; then
    python3 -m venv btc_env
fi

# Активация виртуального окружения
source btc_env/bin/activate

# Обновление pip
print_status "Обновление pip..."
pip install --upgrade pip setuptools wheel

# Установка основных зависимостей
print_status "Установка основных Python пакетов..."
pip install \
    bip-utils==2.9.3 \
    bitcoinlib==0.7.5 \
    requests \
    embit \
    mnemonic

# Установка дополнительных зависимостей
print_status "Установка дополнительных пакетов..."
pip install \
    pandas \
    openpyxl \
    aiohttp \
    aiosignal \
    numpy

# Создание безопасных директорий
print_status "Создание директорий..."
mkdir -p secure hits exports mass_exports logs
chmod 700 secure hits

# Настройка .gitignore для безопасности
if [[ ! -f ".gitignore" ]] || ! grep -q "secure/" .gitignore; then
    cat >> .gitignore << 'EOF'

# Дополнительная безопасность
secure/
hits/
*.mnemonic
*_private*
*_secret*
private_keys/
*.wif
*.key
*.priv
EOF
fi

# Создание конфигурационного файла
print_status "Создание конфигурационного файла..."
cat > config.json << 'EOF'
{
  "default_network": "bitcoin",
  "default_witness": "segwit",
  "workers": 4,
  "delay_ms": 150,
  "export_dir": "./exports",
  "secure_dir": "./secure",
  "hits_dir": "./hits"
}
EOF

# Создание алиасов
print_status "Создание удобных алиасов..."
BASHRC_ADDITION="
# Bitcoin Wallet Tools aliases
alias btc-activate='source $WORK_DIR/Btc_check/btc_env/bin/activate'
alias btc-gen='python3 $WORK_DIR/Btc_check/wallet_tool.py'
alias btc-mass='python3 $WORK_DIR/Btc_check/mass_wallet_tool.py'
alias btc-hits='python3 $WORK_DIR/Btc_check/show_hits.py'
alias btc-batch='python3 $WORK_DIR/Btc_check/batch_wallets.py'
alias btc-cd='cd $WORK_DIR/Btc_check'
"

if ! grep -q "Bitcoin Wallet Tools aliases" ~/.bashrc; then
    echo "$BASHRC_ADDITION" >> ~/.bashrc
    print_success "Алиасы добавлены в ~/.bashrc"
fi

# Создание скрипта быстрого запуска
print_status "Создание скрипта быстрого запуска..."
cat > btc_quick_start.sh << 'EOF'
#!/bin/bash
# Быстрый запуск Bitcoin Wallet Tools

cd "$(dirname "$0")"
source btc_env/bin/activate

echo "🚀 Bitcoin Wallet Tools активированы!"
echo ""
echo "Доступные команды:"
echo "  btc-gen    - Генерация кошельков (wallet_tool.py)"
echo "  btc-mass   - Массовая обработка (mass_wallet_tool.py)" 
echo "  btc-hits   - Просмотр результатов (show_hits.py)"
echo "  btc-batch  - Пакетная обработка (batch_wallets.py)"
echo ""
echo "Пример: btc-gen --help"
echo ""

exec bash
EOF

chmod +x btc_quick_start.sh

# Создание примера файла заданий
print_status "Создание примера конфигурации заданий..."
cat > example_batch_jobs.json << 'EOF'
{
  "jobs": [
    {
      "type": "gen",
      "wallet": "test_wallet",
      "network": "testnet",
      "witness": "segwit",
      "accounts": [0],
      "start": 0,
      "count": 10,
      "out_dir": "./test_exports"
    }
  ]
}
EOF

# Проверка установки
print_status "Проверка установки..."

# Тест импорта модулей
if python3 -c "import bip_utils, bitcoinlib, requests, embit; print('✓ Все модули успешно импортированы')" 2>/dev/null; then
    print_success "Все зависимости установлены корректно"
else
    print_error "Проблема с зависимостями"
    exit 1
fi

# Тест основных скриптов
if python3 wallet_tool.py --help >/dev/null 2>&1; then
    print_success "wallet_tool.py работает"
else
    print_warning "Проблема с wallet_tool.py"
fi

if python3 mass_wallet_tool.py --help >/dev/null 2>&1; then
    print_success "mass_wallet_tool.py работает"
else
    print_warning "Проблема с mass_wallet_tool.py"
fi

# Windows интеграция для WSL
if grep -q "Microsoft\|WSL" /proc/version 2>/dev/null; then
    print_status "Настройка интеграции с Windows..."
    
    # Получение имени пользователя Windows
    WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n' || echo "YourUsername")
    
    cat > windows_integration.sh << EOF
#!/bin/bash
# Интеграция с Windows для WSL

export WINDOWS_DESKTOP="/mnt/c/Users/$WIN_USER/Desktop"
export WINDOWS_DOWNLOADS="/mnt/c/Users/$WIN_USER/Downloads"
export BTC_RESULTS_DIR="\$WINDOWS_DESKTOP/btc_results"

# Создание директории результатов на рабочем столе Windows
mkdir -p "\$BTC_RESULTS_DIR"

echo "Windows интеграция настроена:"
echo "  Рабочий стол: \$WINDOWS_DESKTOP"
echo "  Результаты: \$BTC_RESULTS_DIR"
EOF
    
    chmod +x windows_integration.sh
    
    print_success "Интеграция с Windows настроена"
fi

print_success "🎉 Установка завершена!"
print_status ""
print_status "Для начала работы:"
print_status "1. Перезагрузите терминал или выполните: source ~/.bashrc"
print_status "2. Перейдите в директорию: cd $WORK_DIR/Btc_check"  
print_status "3. Запустите: ./btc_quick_start.sh"
print_status ""
print_status "Или используйте алиасы:"
print_status "  btc-activate  # Активация окружения"
print_status "  btc-cd        # Переход в директорию проекта"
print_status "  btc-gen --help    # Справка по генерации"
print_status "  btc-mass --help   # Справка по массовой обработке"
print_status ""
print_warning "⚠️  ВАЖНО: Храните приватные ключи и мнемоники в безопасности!"
print_warning "   Папка 'secure/' защищена правами доступа 700"