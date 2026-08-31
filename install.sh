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
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

print_header() {
    clear
    echo ""
    echo -e "  ${CYAN}╔═════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║             🎬 AI MOVIE SHORTS BOT — ИНСТАЛЛЯТОР ДЛЯ LINUX              ║${NC}"
    echo -e "  ${CYAN}║     (Поддержка CachyOS, Arch, Ubuntu, Debian, Fedora, openSUSE)         ║${NC}"
    echo -e "  ${CYAN}╚═════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${GRAY}📁 Рабочая папка: ${WHITE}$(pwd)${NC}"
    echo ""
}

print_step() {
    local step_num="$1"
    local step_title="$2"
    echo ""
    echo -e "  ${GRAY}─────────────────────────────────────────────────────────────────────────${NC}"
    echo -e "  ${MAGENTA}${BOLD}[ШАГ ${step_num}]${NC} ${WHITE}${BOLD}${step_title}${NC}"
    echo -e "  ${GRAY}─────────────────────────────────────────────────────────────────────────${NC}"
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
            printf "  ${YELLOW}?${NC} ${WHITE}%s${NC} ${GRAY}[По умолчанию: %s]${NC}: " "$question" "$default_val"
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
                echo -e "    ${RED}[!] Это поле обязательно для заполнения. Попробуйте снова.${NC}" >&2
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
        echo -e "  ${YELLOW}[i] Для установки системных утилит могут потребоваться права администратора.${NC}"
        echo -e "  ${YELLOW}[i] Введите пароль пользователя при появлении запроса [sudo].${NC}"
        echo ""
    else
        echo -e "  ${RED}[✗] Скрипт требует прав администратора (root или sudo).${NC}"
        exit 1
    fi
fi

print_step "1/4" "Установка системных зависимостей (Python, FFmpeg, aria2)"

if command -v pacman >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен менеджер пакетов pacman (CachyOS / Arch Linux)${NC}"
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
        glib2

elif command -v apt-get >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен менеджер пакетов apt (Ubuntu / Debian)${NC}"
    $SUDO apt-get update
    $SUDO apt-get install -y \
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
        build-essential

elif command -v dnf >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен менеджер пакетов dnf (Fedora / RHEL)${NC}"
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
        gcc gcc-c++

elif command -v zypper >/dev/null 2>&1; then
    echo -e "  ${CYAN}[i] Обнаружен менеджер пакетов zypper (openSUSE)${NC}"
    $SUDO zypper install -y \
        python3 \
        python3-pip \
        ffmpeg \
        aria2 \
        git \
        curl \
        unzip \
        libGL1 \
        glib2
else
    echo -e "  ${YELLOW}[!] Пакетный менеджер не определен. Убедитесь, что python, ffmpeg и aria2 установлены.${NC}"
fi

echo ""
echo -e "  ${GREEN}[✓] Все системные пакеты успешно установлены!${NC}"

print_step "2/4" "Проверка файлов проекта"

if [ ! -f "bot.py" ]; then
    echo -e "  ${YELLOW}[*] Файлы проекта не найдены в текущей папке.${NC}"
    echo -e "  ${GRAY}[*] Клонирование из репозитория GitHub (${REPO_OWNER}/${REPO_NAME})...${NC}"

    cloned=false
    if command -v git >/dev/null 2>&1; then
        if git clone "https://github.com/${REPO_OWNER}/${REPO_NAME}.git" . --quiet 2>/dev/null; then
            cloned=true
        fi
    fi

    if [ "$cloned" = false ] || [ ! -f "bot.py" ]; then
        echo -e "  ${GRAY}[*] Загрузка ZIP-архива репозитория...${NC}"
        zip_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${REPO_BRANCH}.zip"
        curl -sSL "$zip_url" -o repo.zip
        unzip -q repo.zip
        mv "${REPO_NAME}-${REPO_BRANCH}"/* .
        mv "${REPO_NAME}-${REPO_BRANCH}"/.* . 2>/dev/null || true
        rm -rf repo.zip "${REPO_NAME}-${REPO_BRANCH}"
    fi
    echo -e "  ${GREEN}[✓] Файлы бота успешно загружены!${NC}"
else
    echo -e "  ${GREEN}[✓] Файлы проекта уже находятся в текущей папке.${NC}"
fi

print_step "3/4" "Настройка конфигурации (.env)"

bot_token=$(ask_input "Telegram Bot Token (полученный у @BotFather)" "" "true" "false")
openai_key=$(ask_input "OpenAI / OpenRouter API ключ" "" "true" "true")
base_url=$(ask_input "OpenAI Base URL" "https://api.openai.com/v1" "false" "false")
model_name=$(ask_input "Модель LLM (например: gpt-4o, deepseek-chat)" "gpt-4o" "false" "false")

echo ""
echo -e "  ${WHITE}Выберите модель Whisper для распознавания речи:${NC}"
echo -e "    ${CYAN}1)${NC} ${WHITE}large-v3-turbo${NC} ${GRAY}(Рекомендуется: максимальная точность и быстрая работа)${NC}"
echo -e "    ${CYAN}2)${NC} ${WHITE}medium${NC}         ${GRAY}(Средний баланс)${NC}"
echo -e "    ${CYAN}3)${NC} ${WHITE}small${NC}          ${GRAY}(Для слабых ПК / медленных процессоров)${NC}"
whisper_choice=$(ask_input "Ваш выбор [1-3]" "1" "false" "false")

case "$whisper_choice" in
    2) whisper_model="medium" ;;
    3) whisper_model="small" ;;
    *) whisper_model="large-v3-turbo" ;;
esac

echo ""
echo -e "  ${WHITE}Выберите устройство для обработки Whisper:${NC}"
echo -e "    ${CYAN}1)${NC} ${WHITE}CPU${NC}  ${GRAY}(Процессор, работает абсолютно везде)${NC}"
echo -e "    ${CYAN}2)${NC} ${WHITE}CUDA${NC} ${GRAY}(Видеокарта NVIDIA с установленными драйверами)${NC}"
device_choice=$(ask_input "Ваш выбор [1-2]" "1" "false" "false")

if [ "$device_choice" = "2" ]; then
    whisper_device="cuda"
    whisper_compute="float16"
else
    whisper_device="cpu"
    whisper_compute="int8"
fi

http_proxy=$(ask_input "HTTP Прокси (если требуется, например: http://127.0.0.1:10809, иначе Enter)" "" "false" "false")
max_clips=$(ask_input "Максимальное количество клипов за одну генерацию" "5" "false" "false")

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

echo ""
echo -e "  ${GREEN}[✓] Файл .env успешно сгенерирован и сохранен!${NC}"

print_step "4/4" "Создание окружения Python и установка библиотек"

if [ ! -d ".venv" ]; then
    echo -e "  ${GRAY}[*] Создание виртуального окружения (.venv)...${NC}"
    python3 -m venv .venv
fi

echo -e "  ${GRAY}[*] Обновление pip и установка requirements.txt...${NC}"
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

cat <<'EOF' > start.sh
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python3 bot.py
EOF
chmod +x start.sh

echo ""
echo -e "  ${GREEN}╔═════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║                     УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!                        ║${NC}"
echo -e "  ${GREEN}╚═════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${WHITE}Для последующего запуска используйте команду:${NC}"
echo -e "    ${YELLOW}./start.sh${NC}"
echo ""

start_now=$(ask_input "Запустить бота прямо сейчас? (y/n)" "y" "false" "false")
if [ "$(echo "$start_now" | tr '[:upper:]' '[:lower:]')" = "y" ]; then
    ./.venv/bin/python3 bot.py
fi
