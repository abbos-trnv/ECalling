# ADR 0001: локальная основа на Windows

Статус: принято, 2026-11-06.

FastAPI + PostgreSQL + React/Vite, один репозиторий. Docker Compose
позволяет запустить всё из PowerShell. Ubuntu как отдельная рабочая среда
не требуется; Docker Desktop использует свой Linux backend (обычно WSL2).
Сервисы публикуются только на 127.0.0.1.

Python-зависимости ведём через uv и uv.lock. Frontend — npm с package-lock.json:
дополнительный пакетный менеджер pnpm для прототипа не нужен.
psycopg обеспечивает проверку настоящего соединения с PostgreSQL;
pydantic-settings читает окружение. pytest/httpx и Ruff проверяют API и стиль.
Без брокера, GPU и модельных зависимостей на этапе V0-00.

HTTP-контракты основы: GET /health/live (200 без БД), GET /health/ready
(200 при SELECT 1, иначе 503 без раскрытия исключения), GET /api/v1/system
(локальный режим и доступность pipeline). Эти маршруты не являются авторизацией.

Vite используется только как локальный dev server. Развёртывание в интернете,
production frontend serving и реальные данные в этот этап не входят.
