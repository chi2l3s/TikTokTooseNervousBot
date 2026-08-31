#!/usr/bin/env bash
set -e

[ -t 0 ] || exec < /dev/tty 2>/dev/null || true

REPO_OWNER="chi2l3s"
REPO_NAME="TikTokTooseNervousBot"
REPO_BRANCH="main"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m'

print_header() {
    clear
    echo ""
    echo -e "  ${CYAN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║           🎬 AI MOVIE SHORTS BOT INSTALLER (UNIVERSAL LINUX)      ║${NC}"
    echo -e "  ${CYAN}║         Автоматическая установка и интерактивная настройка        ║${NC}"
    echo -e "  ${CYAN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${GRAY}[i] Рабочая директория: $(pwd)${NC}"
    echo ""
}

ask_input() {
    local question="$1"
    local default_val="$2"
    local required="$3"
    local is_secret="$4"
    local input_val=""

    while true; do
        if [ -n "$default_val" ]; then
            printf "  ${YELLOW}?${NC} ${WHITE}%s${NC} ${GRAY}[%s]${NC}: " "$question" "$default_val"
        else
            printf "  ${YELLOW}?${NC} ${WHITE}%s${NC}: " "$question"
        fi

        if [ "$is_secret" = "true" ]; then
            read -s -r input_val
            echo ""
        else
            read -r input_val
        fi

        input_val=$(echo "$input_val" | xargs)

        if [ -z "$input_val" ]; then
            if [ -n "$default_val" ]; then
                echo "$default_val"
                return 0
            elif [ "$required" = "true" ]; then
                echo -e "    ${RED}[!] Это обязательное поле, попробуйте снова.${NC}" >&2
                continue
            else
                echo ""
                return 0
            fi
        fi

        echo "$input_val"
        return 0
    done
}

print_header

SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "  ${RED}[✗] Скрипт требует прав администратора (root или sudo).${NC}"
        exit 1
    fi
fi

# 1. Определение дистрибутива и установка пакетов
echo -e "  ${GRAY}[*] Определение дистрибутива Linux и установка системных зависимостей...${NC}"

if command -v pacman >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен CachyOS / Arch Linux (pacman)${NC}"
    $SUDO pacman -Sy --needed --noconfirm \
        python \
        python-pip \
        ffmpeg \
        aria2 \
        git \
        curl \
        unzip \
        base-devel \
        libglvnd \
        glib2 >/dev/null 2>&1

elif command -v apt-get >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен Debian / Ubuntu (apt)${NC}"
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq \
        python3 \
        python3-venv \
        python3-pip \
        ffmpeg \
        aria2 \
        git \
        curl \
        unzip \
        libgl1 \
        libglib2.0-0 \
        build-essential >/dev/null 2>&1

elif command -v dnf >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен Fedora / RHEL (dnf)${NC}"
    $SUDO dnf install -y \
        python3 \
        python3-pip \
        ffmpeg \
        aria2 \
        git \
        curl \
        unzip \
        mesa-libGL \
        glib2 \
        gcc gcc-c++ >/dev/null 2>&1

elif command -v zypper >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен openSUSE (zypper)${NC}"
    $SUDO zypper install -y \
        python3 \
        python3-pip \
        ffmpeg \
        aria2 \
        git \
        curl \
        unzip \
        libGL1 \
        glib2 >/dev/null 2>&1
else
    echo -e "  ${YELLOW}[!] Пакетный менеджер не определен. Убедитесь, что python3, ffmpeg и aria2 установлены.${NC}"
fi

echo -e "  ${GREEN}[✓] Системные зависимости готовы!${NC}"

# 2. Клонирование репозитория
if [ ! -f "bot.py" ]; then
    echo -e "  ${YELLOW}[*] Файлы проекта не обнаружены в текущей папке.${NC}"
    echo -e "  ${GRAY}[*] Загрузка проекта из GitHub ($REPO_OWNER/$REPO_NAME)...${NC}"

    cloned=false
    if command -v git >/dev/null 2>&1; then
        if git clone "https://github.com/$REPO_OWNER/$REPO_NAME.git" . --quiet 2>/dev/null; then
            cloned=true
        fi
    fi

    if [ "$cloned" = false ] || [ ! -f "bot.py" ]; then
        echo -e "  ${GRAY}[*] Скачивание архива репозитория...${NC}"
        zip_url="https://github.com/$REPO_OWNER/$REPO_NAME/archive/refs/heads/$REPO_BRANCH.zip"
        curl -sSL "$zip_url" -o repo.zip
        unzip -q repo.zip
        mv "$REPO_NAME-$REPO_BRANCH"/* .
        mv "$REPO_NAME-$REPO_BRANCH"/.* . 2>/dev/null || true
        rm -rf repo.zip "$REPO_NAME-$REPO_BRANCH"
    fi
    echo -e "  ${GREEN}[✓] Проект успешно загружен!${NC}"
fi

echo ""
echo -e "  ${GRAY}───────────────────────────────────────────────────────────────────${NC}"
echo -e "  ${CYAN}                 ШАГ 1: НАСТРОЙКА ПАРАМЕТРОВ БОТА                  ${NC}"
echo -e "  ${GRAY}───────────────────────────────────────────────────────────────────${NC}"
echo ""

bot_token=$(ask_input "Введите Telegram Bot Token (от @BotFather)" "" "true" "false")
openai_key=$(ask_input "Введите OpenAI / OpenRouter API ключ" "" "true" "true")
base_url=$(ask_input "OpenAI Base URL" "https://api.openai.com/v1" "false" "false")
model_name=$(ask_input "Модель LLM" "gpt-4o" "false" "false")

echo ""
echo -e "  ${GRAY}Выберите модель Whisper для распознавания речи:${NC}"
echo -e "    ${WHITE}1) large-v3-turbo (Максимальная точность, рекомендуется)${NC}"
echo -e "    ${WHITE}2) medium         (Хороший баланс)${NC}"
echo -e "    ${WHITE}3) small          (Быстрая, для слабых ПК)${NC}"
whisper_choice=$(ask_input "Выберите вариант [1-3]" "1" "false" "false")

case "$whisper_choice" in
    2) whisper_model="medium" ;;
    3) whisper_model="small" ;;
    *) whisper_model="large-v3-turbo" ;;
esac

echo ""
echo -e "  ${GRAY}Устройство для Whisper:${NC}"
echo -e "    ${WHITE}1) CPU (Процессор, по умолчанию)${NC}"
echo -e "    ${WHITE}2) CUDA (Видеокарта NVIDIA)${NC}"
device_choice=$(ask_input "Выберите устройство [1-2]" "1" "false" "false")

if [ "$device_choice" = "2" ]; then
    whisper_device="cuda"
    whisper_compute="float16"
else
    whisper_device="cpu"
    whisper_compute="int8"
fi

http_proxy=$(ask_input "HTTP Прокси (если нужен, например: http://127.0.0.1:10809, иначе пусто)" "" "false" "false")
max_clips=$(ask_input "Максимум клипов за раз" "5" "false" "false")

echo ""
echo -e "  ${GRAY}───────────────────────────────────────────────────────────────────${NC}"
echo -e "  ${CYAN}               ШАГ 2: СОЗДАНИЕ ОКРУЖЕНИЯ И БАЗЫ ДАННЫХ             ${NC}"
echo -e "  ${GRAY}───────────────────────────────────────────────────────────────────${NC}"
echo ""

mkdir -p music temp fonts

cat <<EOF > .env
BOT_TOKEN=$bot_token
OPENAI_API_KEY=$openai_key
OPENAI_BASE_URL=$base_url
OPENAI_MODEL=$model_name
WHISPER_MODEL=$whisper_model
WHISPER_DEVICE=$whisper_device
WHISPER_COMPUTE_TYPE=$whisper_compute
HTTP_PROXY=$http_proxy
MAX_CLIPS=$max_clips
EOF

echo -e "  ${GREEN}[✓] Конфигурация .env успешно создана!${NC}"

# Виртуальное окружение
if [ ! -d ".venv" ]; then
    echo -e "  ${GRAY}[*] Создание виртуального окружения (.venv)...${NC}"
    python3 -m venv .venv
fi

echo -e "  ${GRAY}[*] Установка зависимостей из requirements.txt...${NC}"
./.venv/bin/pip install --upgrade pip --quiet
./.venv/bin/pip install -r requirements.txt --quiet

# Создание скрипта запуска start.sh
cat <<'EOF' > start.sh
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python3 bot.py
EOF
chmod +x start.sh

echo ""
echo -e "  ${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║                   УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!                    ║${NC}"
echo -e "  ${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${WHITE}Для запуска бота используйте:${NC}"
echo -e "    ${YELLOW}./start.sh${NC}"
echo ""

start_now=$(ask_input "Запустить бота прямо сейчас в консоли? (y/n)" "y" "false" "false")
if [ "$(echo "$start_now" | tr '[:upper:]' '[:lower:]')" = "y" ]; then
    ./.venv/bin/python3 bot.py
fi