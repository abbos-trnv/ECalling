# Voice Analytics · V0

Локальный прототип анализа звонков. Реализуется поэтапно по [спецификации V0.2](docs/spec-v02.md).
Завершены **V0-00: основа**, **V0-01: компании и сотрудники**,
**V0-02: загрузка аудио и очередь проверки**.
Завершён **V0-03: сквозной mock-процесс, транскрипт и анализ**.
Есть создание, переименование и удаление компаний и сотрудников, выбор компании,
постоянное хранение в PostgreSQL, миграции и тестовые данные.
Работают загрузка WAV/MP3/M4A, список записей, плеер с Range, SQL-очередь и
отдельный worker. MockASR/MockLLM создают вымышленный пример транскрипта и анализа,
явно отмеченный MOCK. Это не распознавание и не анализ содержимого аудио.
Реальные ASR/LLM ещё не подключены. Роли говорящих unknown: оценка сотрудника
не определяется (score=null), а не становится нулём.

**Проверено 2026-11-06:** API, PostgreSQL, web и worker запущены;
35 тестов прошли внутри Docker с настоящими ffmpeg/ffprobe и PostgreSQL,
включая схемы mock-вывода, scorer, историю результатов и fencing публикации.
Первоначальное зависание Docker/WSL устранено после полного перезапуска WSL.
Подробности —
[журнал проверки V0-00](docs/verification-v0-00.md) и
[проверку V0-01](docs/verification-v0-01.md). Очередь описана в
[ADR V0-02](docs/decisions/0003-audio-queue.md).
Контракт mock-процесса — [ADR V0-03](docs/decisions/0004-mock-pipeline.md).

## Windows: запуск через Docker Desktop

Нужен Docker Desktop с работающим Linux backend. Установка Ubuntu отдельно
не требуется. Команды из PowerShell в корне проекта:

```powershell
docker compose -f infra/compose.yaml up --build -d --wait
docker compose -f infra/compose.yaml exec -T api python -m apps.api.seed
```

- Интерфейс: http://127.0.0.1:5173
- API OpenAPI: http://127.0.0.1:8000/docs
- Готовность БД и API: http://127.0.0.1:8000/health/ready

Первый запуск скачивает образы и зависимости. PostgreSQL хранит данные в named
volume. Пароль в Compose — фиксированный пароль локального демо. Порты слушают
только loopback. Не публиковать эту конфигурацию в интернете.

Одноразовый сервис `migrate` применяет миграции до старта API. Его статус
`Exited (0)` нормален. Seed создаёт `ООО Ромашка`, `ООО Вектор` и по два агента
в каждой компании. Повтор команды не создаёт дублей и не меняет существующие
имена; явно удалённые тестовые записи восстанавливаются при повторном seed.
Обычный перезапуск приложения seed не выполняет.

В блоке «Записи звонков» выберите файл и, при необходимости, сотрудника.
Используется компания, выбранная в блоке выше. Лимиты по умолчанию — 50 MiB и
30 минут. API проверяет формат и длительность, worker полностью декодирует
аудиодорожку. Новые записи в mock-режиме проходят `queued → processing → completed`
либо `failed`. `completed` в этом режиме означает готовый вымышленный пример.
Старые preprocess-запуски сохраняют `awaiting_analysis` до ручного запуска mock.
Расширение и MIME из запроса не считаются подтверждением формата.

Для старой записи нажмите «Создать тестовый результат (mock)». Для готовой —
«Открыть тестовый результат». В карточке есть вымышленный транскрипт с таймкодами,
категории/возражения, пять критериев и версия чек-листа. Таймкод запускает исходный
плеер с условного момента; он не подтверждает наличие вымышленной реплики в аудио.
Кнопка «Повторить mock» создаёт новую версию, старые доступны через «Версия обработки».
Старые результаты не перезаписываются.

Чек-лист: `apps/api/config/scorecard-demo-v1.json`. Настройки/веса копируются
в каждый run; при изменении конфигурации повышайте version. Unknown и N/A не
считаются провалом. Если нет оцениваемых критериев, score=null. Coverage —
доля оценённых весов среди применимых и неопределённых; N/A исключается.

Аудио хранится отдельно от БД в Docker volume `voice-analytics_audio_data`.
Обычный `docker compose down` сохраняет оба volume. Не выполняйте `down -v`
или Docker factory reset, если нужны записи и данные.

Настройки лимитов из .env.example передаются в Compose. Worker работает
с одной задачей одновременно, продлевает lease и восстанавливает истёкшие
аренды с ограничением в 3 попытки. Распознавание речи пока не запускается.

В интерфейсе блок «Компании и сотрудники» позволяет выбрать компанию,
добавить сотрудника, изменить имя и удалить запись после подтверждения.
Удаление компании с сотрудниками или звонками блокируется. Сотрудник, связанный
со звонками, тоже не удаляется. Удаление самих звонков будет добавлено позднее.
Сотрудники показываются по 10 на страницу.

```powershell
docker compose -f infra/compose.yaml logs --tail 80
docker compose -f infra/compose.yaml down
```

`down` сохраняет данные БД. Не добавлять `-v`, если они нужны.

## Разработка без контейнеров для API / web

Нужны обычный CPython 3.12+ (не MSYS Python), uv, Node.js 22.12+ или 24, npm
и ffmpeg/ffprobe в PATH (для загрузки/проверки аудио).
Базу всё равно запускаем через Docker:

```powershell
docker compose -f infra/compose.yaml up -d db
Copy-Item .env.example .env
uv sync --frozen
uv run alembic upgrade head
uv run python -m apps.api.seed
uv run uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

В другом терминале:

```powershell
uv run python -m apps.worker
```

И ещё в одном:

```powershell
Set-Location apps/web
npm ci
npm run dev
```

## Проверки

```powershell
uv run ruff check apps tests
uv run ruff format --check apps tests
uv run pytest
npm --prefix apps/web run build
```

Для интеграционных тестов требуется PostgreSQL. Тесты создают и удаляют только
свои случайные схемы `test_<uuid>`; таблицы приложения не меняются:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://voice:voice_local_demo@127.0.0.1:15432/voice_analytics'
uv run pytest
```

Без `TEST_DATABASE_URL` проходят 15 unit-тестов, 20 интеграционных пропускаются.
Без ffmpeg/ffprobe дополнительно пропускаются 12 медиа/pipeline-тестов. CI устанавливает
ffmpeg и запускает все проверки с отдельной PostgreSQL.

Или backend внутри Docker:

```powershell
docker compose -f infra/compose.yaml run --rm api uv run pytest
docker compose -f infra/compose.yaml run --rm api uv run ruff check apps tests
docker compose -f infra/compose.yaml exec -T -e TEST_DATABASE_URL=postgresql://voice:voice_local_demo@db:5432/voice_analytics api python -m pytest -q
```

Проверки покрывают health, CRUD, разделение сотрудников по компаниям, ограничения
PostgreSQL, пагинацию, повторный seed, upgrade/downgrade миграции в тестовой схеме
и отсутствие секретов в ошибках. Для smoke после запуска всех контейнеров:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
```

Медиа-тесты дополнительно проверяют форматы по содержимому, плохое аудио,
лимиты размера/длительности, очистку временных файлов, идемпотентность,
привязку к компании, Range/206, fencing старой аренды, лимит попыток и
восстановление задачи после принудительного завершения процесса-владельца lease.
Все тестовые файлы синтетические. В БД приложения оставлен один `demo-upload.wav`
(2 секунды синтетического тона) для проверки плеера; это не тест качества ASR.

Mock-тесты проверяют схему транскрипта и доказательств, защиту ID/is_mock/score
от candidate-полей, формулу score/coverage, невалидный вывод без публикации,
историю запусков, запрет UPDATE опубликованного результата и fencing публикации.
API: GET `/calls/{call_id}/transcript`, GET `/calls/{call_id}/analysis`, GET
`/calls/{call_id}/runs`, POST `/calls/{call_id}/retry` — внутри
`/api/v1/companies/{company_id}`. Для старой версии transcript/analysis принимают
query `run_id`. 409 — результат ещё не опубликован; чужой call/run — 404.

## Дальше

1. V0-04: настоящее распознавание речи на CPU и замеры скорости.
2. V0-05: реальный LLM-анализ с проверкой структуры и доказательств.
3. Простые агрегаты, качество моделей и оставшиеся критерии полного V0.
