# V0-00: состояние проверки — 2026-11-06

**Итог: V0-00 завершён.** После полного перезапуска WSL Docker восстановился
с задержкой; перезагрузка Windows не потребовалась. Точная причина первоначального
зависания не установлена. Все контейнеры проекта CVAT остановлены с разрешения
пользователя, данные и настройки автозапуска не удалялись.

Повторная проверка:

- Docker API image собран успешно с uv.lock.
- `docker compose -f infra/compose.yaml up -d --wait --no-build` — exit 0.
- API и PostgreSQL healthy; база доступна на 127.0.0.1:15432.
- `powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1` — exit 0:
  API, настоящая PostgreSQL, web и проксирование API работают.
- В API-контейнере (Python 3.12.16): pytest — 4 passed, exit 0;
  Ruff check и format --check — exit 0.
- Нативный временный Uvicorn остановлен, API работает только в Docker.
- Удалённый CI не запускался. Модельный pipeline пока не реализован.

Ниже сохранён журнал первоначальной диагностики; перечисленные блокировки
устранены при повторном запуске.

Созданы FastAPI, PostgreSQL Compose, React/Vite/TypeScript, lock-файлы,
CI-конфигурация, smoke-скрипт и README. Исходная спецификация сохранена
в spec-v02.md. Функции компаний, upload, worker и модельного pipeline ещё не созданы.

## Подтверждено

- Windows, CPython 3.13.7: `python -m pytest -q` — exit 0, 4 passed.
  Есть предупреждение Starlette о будущем переходе TestClient с httpx на httpx2.
- `python -m ruff check apps tests` — exit 0.
- `python -m ruff format --check apps tests` — exit 0.
- Docker-сборка web: `tsc --noEmit && vite build` — exit 0.
- Стартовый экран открыт в браузере; сообщение о недоступной БД отображается.
- Нативный Uvicorn отвечает на /health/live: `{"status":"ok"}`.
- `docker compose -f infra/compose.yaml config --quiet` — exit 0.

## Первоначальные блокировки (устранены)

- API Docker image: первая сборка прервана ошибкой DNS files.pythonhosted.org;
  повторные сборки прерваны при восстановлении зависшего Docker.
- PostgreSQL не запущена: bind 127.0.0.1:5433 был отклонён Windows;
  конфигурация перенесена на 15432, повторный старт завис в Docker.
- Docker перестал выполнять start/stop контейнеров. Штатный restart,
  принудительный stop/start и завершение docker-desktop не восстановили движок.
  С разрешения пользователя начат полный `wsl --shutdown`; команда также зависла.
- Остановка контейнеров CVAT была разрешена и отправлена, но подтвердить её
  через Docker не удалось. Docker Desktop принудительно остановлен при восстановлении.
- Полный Compose startup, readiness с настоящей БД и scripts/smoke.ps1
  пока НЕ прошли. CI на удалённом сервере не запускался.

## Выполненный план восстановления (перезагрузка Windows не понадобилась)

1. Запустить Docker Desktop, проверить `docker info`.
2. Если CVAT автоматически стартует, остановить его контейнеры: пользователь
   разрешил временную остановку без удаления данных.
3. Выполнить команду Compose из README, дождаться healthy API.
4. Запустить scripts/smoke.ps1 и проверить страницу в браузере.
5. После успешного запуска V0-00 отмечен завершённым. Следующая задача — V0-01.

Ничего не удалять из Docker volumes, не сбрасывать Docker к заводским настройкам.
