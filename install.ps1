$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoOwner = "ВАШ_АККАУНТ"
$RepoName = "ВАШ_РЕПОЗИТОРИЙ"
$RepoBranch = "main"

function Print-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                🎬 AI MOVIE SHORTS BOT INSTALLER                   ║" -ForegroundColor Cyan
    Write-Host "  ║         Автоматическая установка и интерактивная настройка        ║" -ForegroundColor Cyan
    Write-Host "  ╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Ask-Input {
    param (
        [string]$Question,
        [string]$Default = "",
        [bool]$Required = $false,
        [bool]$IsSecret = $false
    )
    while ($true) {
        if ($Default) {
            Write-Host "  ? " -ForegroundColor Yellow -NoNewline
            Write-Host "$Question " -ForegroundColor White -NoNewline
            Write-Host "[$Default]: " -ForegroundColor DarkGray -NoNewline
        } else {
            Write-Host "  ? " -ForegroundColor Yellow -NoNewline
            Write-Host "$Question: " -ForegroundColor White -NoNewline
        }

        if ($IsSecret) {
            $inputVal = Read-Host -AsSecureString
            $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($inputVal)
            $val = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        } else {
            $val = Read-Host
        }

        if ([string]::IsNullOrWhiteSpace($val)) {
            if ($Default) { return $Default }
            if ($Required) {
                Write-Host "    [!] Это обязательное поле, попробуйте снова." -ForegroundColor Red
                continue
            }
            return ""
        }
        return $val.Trim()
    }
}

Print-Header

# 1. Проверка и клонирование репозитория
if (-not (Test-Path "bot.py")) {
    Write-Host "  [*] Файлы проекта не обнаружены в текущей папке." -ForegroundColor Yellow
    Write-Host "  [*] Загрузка проекта из GitHub ($RepoOwner/$RepoName)..." -ForegroundColor Gray
    
    $cloned = $false
    try {
        & git --version | Out-Null
        Write-Host "  [*] Клонирование через Git..." -ForegroundColor Gray
        & git clone "https://github.com/$RepoOwner/$RepoName.git" . --quiet
        $cloned = $true
    } catch {
        $cloned = $false
    }

    if (-not $cloned -or (-not (Test-Path "bot.py"))) {
        Write-Host "  [*] Git не найден, загрузка ZIP-архива..." -ForegroundColor Gray
        $zipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$RepoBranch.zip"
        $zipFile = "$PWD\repo.zip"
        $tempExtract = "$PWD\temp_extract"

        Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile
        Expand-Archive -Path $zipFile -DestinationPath $tempExtract -Force
        
        $innerFolder = Get-ChildItem -Path $tempExtract | Select-Object -First 1
        Get-ChildItem -Path $innerFolder.FullName | Move-Item -Destination $PWD -Force
        
        Remove-Item -Path $tempExtract -Recurse -Force
        Remove-Item -Path $zipFile -Force
    }
    Write-Host "  [✓] Проект успешно загружен в текущую папку!" -ForegroundColor Green
}

# 2. Проверка Python
Write-Host "  [*] Проверка зависимостей системы..." -ForegroundColor Gray
try {
    $pyVer = & python --version 2>&1
    Write-Host "  [✓] Найден $pyVer" -ForegroundColor Green
} catch {
    Write-Host "  [✗] Python не найден!" -ForegroundColor Red
    Write-Host "      Устанавливаю Python через winget..." -ForegroundColor Yellow
    winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    Write-Host "  [!] Пожалуйста, перезапустите терминал после установки Python." -ForegroundColor Red
    Exit
}

# 3. Проверка FFmpeg
try {
    & ffmpeg -version | Out-Null
    Write-Host "  [✓] Найден FFmpeg" -ForegroundColor Green
} catch {
    Write-Host "  [!] FFmpeg не обнаружен. Устанавливаю через winget..." -ForegroundColor Yellow
    try {
        winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
        Write-Host "  [✓] FFmpeg успешно установлен!" -ForegroundColor Green
    } catch {
        Write-Host "  [✗] Не удалось установить FFmpeg автоматически. Установите его вручную." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "  ───────────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "                   ШАГ 1: НАСТРОЙКА ПАРАМЕТРОВ БОТА                  " -ForegroundColor Cyan
Write-Host "  ───────────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

$botToken = Ask-Input -Question "Введите Telegram Bot Token (от @BotFather)" -Required $true
$openaiKey = Ask-Input -Question "Введите OpenAI / OpenRouter API ключ" -Required $true -IsSecret $true
$baseUrl = Ask-Input -Question "OpenAI Base URL" -Default "https://api.openai.com/v1"
$modelName = Ask-Input -Question "Модель LLM (gpt-4o / deepseek-chat / anthropic/...)" -Default "gpt-4o"

Write-Host ""
Write-Host "  Выберите модель Whisper для распознавания речи:" -ForegroundColor Gray
Write-Host "    1) large-v3-turbo (Максимальная точность, рекомендуется)" -ForegroundColor White
Write-Host "    2) medium         (Хороший баланс)" -ForegroundColor White
Write-Host "    3) small          (Быстрая, для слабых ПК)" -ForegroundColor White
$whisperChoice = Ask-Input -Question "Выберите вариант [1-3]" -Default "1"

switch ($whisperChoice) {
    "2" { $whisperModel = "medium" }
    "3" { $whisperModel = "small" }
    Default { $whisperModel = "large-v3-turbo" }
}

Write-Host ""
Write-Host "  Устройство для Whisper:" -ForegroundColor Gray
Write-Host "    1) CPU (Процессор, работает у всех)" -ForegroundColor White
Write-Host "    2) CUDA (Видеокарта NVIDIA)" -ForegroundColor White
$deviceChoice = Ask-Input -Question "Выберите устройство [1-2]" -Default "1"

if ($deviceChoice -eq "2") {
    $whisperDevice = "cuda"
    $whisperCompute = "float16"
} else {
    $whisperDevice = "cpu"
    $whisperCompute = "int8"
}

$httpProxy = Ask-Input -Question "HTTP Прокси (если нужен, например: http://127.0.0.1:10809, иначе оставьте пустым)" -Default ""
$maxClips = Ask-Input -Question "Максимум клипов за раз" -Default "5"

Write-Host ""
Write-Host "  ───────────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "                 ШАГ 2: СОЗДАНИЕ ОКРУЖЕНИЯ И ЗАГРУЗКА                 " -ForegroundColor Cyan
Write-Host "  ───────────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Создание директорий
$dirs = @("music", "temp", "fonts")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d | Out-Null
    }
}

# Генерация .env файла
$envContent = @"
BOT_TOKEN=$botToken
OPENAI_API_KEY=$openaiKey
OPENAI_BASE_URL=$baseUrl
OPENAI_MODEL=$modelName
WHISPER_MODEL=$whisperModel
WHISPER_DEVICE=$whisperDevice
WHISPER_COMPUTE_TYPE=$whisperCompute
HTTP_PROXY=$httpProxy
MAX_CLIPS=$maxClips
"@

[System.IO.File]::WriteAllText("$PWD\.env", $envContent, [System.Text.Encoding]::UTF8)
Write-Host "  [✓] Файл конфигурации .env успешно создан!" -ForegroundColor Green

# Виртуальное окружение
if (-not (Test-Path ".venv")) {
    Write-Host "  [*] Создание виртуального окружения (.venv)..." -ForegroundColor Gray
    & python -m venv .venv
}

Write-Host "  [*] Установка библиотек из requirements.txt..." -ForegroundColor Gray
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\pip.exe install -r requirements.txt

# Создание лаунчера start.bat
$launcherContent = @"
@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python bot.py
pause
"@
[System.IO.File]::WriteAllText("$PWD\start.bat", $launcherContent, [System.Text.Encoding]::UTF8)

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║                   УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!                    ║" -ForegroundColor Green
Write-Host "  ╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Для запуска бота используйте команду:" -ForegroundColor White
Write-Host "    .\start.bat" -ForegroundColor Yellow
Write-Host ""

$startNow = Ask-Input -Question "Запустить бота прямо сейчас? (y/n)" -Default "y"
if ($startNow.ToLower() -eq "y") {
    & .\.venv\Scripts\python.exe bot.py
}