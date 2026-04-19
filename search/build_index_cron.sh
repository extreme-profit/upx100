#!/bin/bash
# Скрипт для автоматического обновления векторного индекса в 3 часа ночи
# Добавьте в crontab: 0 3 * * * /path/to/this/script.sh

cd /workspace
source venv/bin/activate 2>/dev/null || true  # Активируем виртуальное окружение если есть
python manage.py build_vector_index >> /var/log/vector_index_build.log 2>&1
