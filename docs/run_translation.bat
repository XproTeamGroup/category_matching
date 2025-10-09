@echo off
chcp 65001 >nul
echo ============================================================
echo Скрипт перекладу категорій з польської на українську
echo ============================================================
echo.

REM Перевірка наявності Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ПОМИЛКА: Python не знайдено!
    echo Встановіть Python з https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Перевірка наявності бібліотеки anthropic
python -c "import anthropic" >nul 2>&1
if errorlevel 1 (
    echo Бібліотека anthropic не встановлена. Встановлюємо...
    pip install anthropic
    if errorlevel 1 (
        echo ПОМИЛКА: Не вдалося встановити бібліотеку anthropic
        pause
        exit /b 1
    )
)

REM Перевірка наявності API ключа
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo УВАГА: Змінна середовища ANTHROPIC_API_KEY не встановлена!
    echo.
    set /p API_KEY="Введіть ваш API ключ Anthropic: "
    set ANTHROPIC_API_KEY=!API_KEY!
)

echo.
echo Запуск скрипта перекладу...
echo.

python translate_categories.py

if errorlevel 1 (
    echo.
    echo ПОМИЛКА: Виникла помилка під час виконання скрипта
) else (
    echo.
    echo Скрипт виконано успішно!
)

echo.
pause
