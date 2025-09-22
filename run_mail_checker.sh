#!/usr/bin/env bash
set -euo pipefail

# Активируем окружение
source /home/sav/projects/ai-assistant/venv/bin/activate

# Переходим в рабочую папку (если скрипт что-то читает из неё)
cd /home/sav/projects/ai-assistant

# Запускаем квикстарт (или твой mail_checker.py)
python quickstart.py
