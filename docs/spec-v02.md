# VOICE ANALYTICS — ПРОТОТИП V0.2

**Техническая документация • 02.11.2026**

Этот документ включает текущие требования V0.2 и приложение об исследовании рынка. Устаревшие pilot requirements не входят в актуальный scope. Код ещё не создан.

---



---

# Voice Analytics — техническая документация для прототипа v0.2

**Дата:** 02.11.2026 · **Статус:** принято как отправная спецификация, не реализовано · **Владелец:** один разработчик + бизнес-партнёр.

## Что мы делаем

Локально запускаемый **вертикальный прототип** AI-речевой аналитики. Пользователь в режиме локального демо создаёт вымышленную компанию, добавляет сотрудников, загружает разрешённую аудиозапись, запускает обработку и просматривает транскрипт с таймкодами, структурированный анализ, оценку по чек-листу и простые агрегаты. Демо нескольких компаний нужно для проверки модели данных, но **это не защищённый SaaS для внешних клиентов**.

**Определение готовности:** новый разработчик может запустить проект по README; создать 2 тестовые компании; загрузить несколько файлов; увидеть статусы `queued → processing → completed/failed`; получить реальный результат из ASR и LLM (либо явно помеченный `mock`); перейти в аудио по ссылке на сегмент; успешно повторить тесты и перезапустить worker без потери заявки.

## Принятый scope

| Сейчас (V0) | Потом, по триггеру |
|---|---|
| Ручной upload, тестовые компании/сотрудники | API-коннекторы к CRM/АТС, webhooks, backfill |
| Локальное демо, без публичного доступа | Реальная аутентификация, RBAC, isolation/security audit |
| FastAPI, PostgreSQL, worker с DB-очередью | Redis/Celery/Temporal только после необходимости |
| Локальное хранилище аудио за `Storage` интерфейсом | Приватный S3, signed URLs, retention/backups |
| faster-whisper CPU или адаптер внешнего ASR | GPU ASR, специализированная адаптация |
| Qwen/Ollama или адаптер внешнего LLM | Hosted LLM, локальный GPU, LoRA/Fine-tuning |
| Диаризация как optional, `unknown` как честный fallback | pyannote, multichannel, role confidence |
| Список звонков, карточка, простые KPI | Полный BI, QA-review workflow, billing |

## Обязательные ограничения

1. Только синтетические записи / записи с законным разрешением. Не использовать материалы реальных клиентов без отдельной юридической и технической подготовки.
2. Не выставлять локальную demo-версию в публичный интернет: в ней ещё нет production-auth и защиты персональных данных.
3. Не выдавать `mock`-результат за инференс. В UI и БД сохранять `asr_provider`/`llm_provider` и `is_mock`.
4. Всё выводимое LLM — недоверенный результат, требующий schema-validation и привязки к существующим `segment_id`.
5. Структурированный код и контракты важнее количества сервисов: не создавать микросервисы, Kafka/K8s и GPU-инфраструктуру заранее.
6. Все вычисления score осуществляются детерминированно в backend; `unknown` и `not_applicable` не равны провалу критерия.

## С чего начать (порядок чтения)

1. `docs/01-product-scope.md` — что строим и чему говорим «нет».
2. `docs/02-architecture.md` — компоненты, границы и поток звонка.
3. `docs/03-local-development.md` — среда Windows/WSL, Docker и команды запуска (целевые, после реализации).
4. `docs/04-data-model.md` и `docs/05-api-contract.md` — модель данных и API.
5. `docs/06-ml-pipeline.md` — откуда берём модели и как идёт инференс.
6. `docs/07-qa-mlops.md`, `docs/08-reliability.md`, `docs/09-security.md` — качество и надёжность.
7. `docs/11-implementation-plan.md` — задачи по этапам с acceptance criteria.
8. `AGENTS.md` / `CLAUDE.md` — рамки для Codex/Claude Code.

## Про комплект

- `contracts/` — **примерные исходные контракты**, не сгенерированные реализацией.
- `adrs/` — архитектурные решения с причинами и условиями пересмотра.
- `docs/14-market-research.md` + `docs/15-sources.md` — исходное исследование рынка и ссылки, **не** обязательный backlog V0.
- `reference/legacy-v0.1/` — прежняя подробная спецификация для этапа пилота; **не использовать как текущие требования при кодогенерации**.
- `FULL_SPEC.md` — все основные материалы одним файлом для чтения/передачи модели.

**Термины:** `MUST` — обязательно для локальной V0; `NEXT` — после её завершения; `PILOT` — до получения/обработки реальных данных компании. Все сроки, цены, SLO и показатели качества — гипотезы до бенчмарков.



---

# 01. PRD: локальный вертикальный прототип V0

## Цель и пользователь

Разработчик и партнёр могут независимо протестировать end-to-end SaaS-сценарий на **вымышленной** компании без участия клиента, телефонии и CRM. V0 — не «нарисованный UI» и не проект из одной ML-функции: должен существовать исполняемый маршрут загрузка → durable job → ASR → LLM → SQL → интерфейс.

## Jobs to be done

- «Создать тестовую компанию и сотрудника».
- «Загрузить 2–3-минутную запись, проверить корректность файла и дождаться результата».
- «Прочитать транскрипт и найти подтверждающую реплику по кнопке».
- «Увидеть структуру: тема, результат, возражения, причины отказа, scorecard».
- «Сравнить результаты нескольких звонков по сотруднику».
- «Переключить `mock` провайдер на реальный без изменения прикладных сущностей».

## P0 функции

1. Режим локального демо с фиксированным пользователем-разработчиком; создание/переключение компаний. Не называется аутентификацией.
2. CRUD компании и сотрудника (минимальные поля). Seed `ООО Ромашка`, `Агент 1/2`.
3. Загрузка `.wav/.mp3/.m4a` (форматы валидацией по содержимому; не доверять расширению). Максимум для V0 по умолчанию **50 MB и 30 минут** — конфигурируемые проектные лимиты, не пропускная способность модели.
4. Очередь в PostgreSQL, асинхронная обработка отдельным процессом, опрос статусов интерфейсом.
5. `mock` ASR/LLM для CI и демо; настоящий faster-whisper CPU (опциональная настройка) + один реальный LLM adapter (Ollama). Переход к реальному режиму без смены API.
6. Канонический транскрипт с `segment_id`, `[start_ms,end_ms]`, `speaker_role=unknown|manager|customer`; отсутствие диаризации показывается явно.
7. Одна редактируемая через версионированный JSON-конфиг **тестовая** scorecard (5 критериев). UI-конструктор не нужен.
8. LLM выдаёт структурированные категории и доказательства по `segment_id`; сервер валидирует ссылки; score вычисляет сервер.
9. Карточка звонка: плеер, текст с таймкодами, выводы, критерии, `unknown` и режим модели (`mock/real`).
10. KPI: количество звонков, completed/failed, средняя оценка **по оценённым**, частота типов возражений; фильтр по компании/сотруднику и дате.
11. Минимальные unit, integration, E2E smoke и ML regression fixtures, воспроизводимая среда.

## ВНЕ V0

- Интернет-доступ и реальные аккаунты пользователей; коммерческие компании, CRM, АТС; внешние webhooks.
- Ручная калибровка множества экспертов, биллинг, роли, квоты, встроенный платежный модуль.
- Риалтайм, ASR training/LoRA, большая аналитическая платформа, sentiment/emotion classification, face/voice biometrics.
- GPU deployment, Kubernetes, Kafka, Redis/Celery, распределённые транзакции.
- Обязательная диаризация: для моно-демо результат без attribution допустим.

## Функциональные критерии приёмки

- Создание двух демо компаний, их сотрудника и звонка через UI; фильтрация звонков по выбранной компании (это проверка UX, **не гарантия tenant security**).
- Несколько повторных запусков одного HTTP upload/idempotency key не создают дубль в рамках компании.
- Worker прерван во время ASR: после рестарта незавершённая работа восстанавливается или помечается явной ошибкой, не исчезает.
- У `completed` результата нет ссылок на отсутствующие сегменты; при ошибке разметки `needs_review/unknown`.
- Mock выставлен как Mock в карточке звонка; реальный inference обозначен конкретными model/provider/version.
- Ошибочный, слишком большой и неподдерживаемый файл получают понятную ошибку; нет исполнения кода из имени файла.
- Если нет оценимых критериев, `score=null`, а не `0`.

## Минимальный чек-лист (пример, не отраслевой стандарт)

| Ключ | Критерий | Вес | Ограничение |
|---|---|---:|---|
| greeting | Менеджер поздоровался | 10 | только если можно установить спикера |
| introduction | Назвал компанию/имя | 15 | unknown при неясной роли |
| needs_discovery | Уточнил потребность | 25 | требуется evidence |
| objection_handling | Ответил на возражение | 30 | N/A если возражения не было |
| next_step | Назначил следующий шаг | 20 | зависит от типа звонка |

**Важно:** без достоверного сопоставления спикеров выводы о поведении конкретного менеджера отмечаются `unknown`; можно тестировать классификацию общих тем без назначения ответственных.

## Локальный прогон

Подготовить два сценария: (A) синтетический звонок с возражением «дорого», (B) разговор без возражений. Контрольные метки хранятся отдельно от `mock` вывода. В качестве временных фикстур разрешается текст/сгенерированное аудио, но нельзя заявлять качество ASR по заранее известной текстовой заглушке.



---

# 02. System design: минимальная архитектура с хорошими границами

## Контекст

```mermaid
flowchart TD
    U[Разработчик в браузере] --> WEB[React/Vite SPA]
    WEB --> API[FastAPI]
    API --> PG[(PostgreSQL)]
    API --> FS[(Local File Storage)]
    W[Отдельный Python worker] --> PG
    W --> FS
    W --> ASR[ASR Adapter]
    W --> LLM[LLM Adapter]
    ASR --> FW[faster-whisper CPU / Mock / API]
    LLM --> OLM[Ollama Qwen / Mock / API]
```

Один **monorepo**, две deployable Python-команды (`api`, `worker`) и один frontend. PostgreSQL запускается контейнером. Приватная локальная папка с файлами для demo. Ollama опционален и **не обязателен** для прохождения CI. Изоляция моделей по adapter interface.

## Границы внутри backend (не отдельные сервисы)

| Модуль | Ответственность | Запрещённые зависимости |
|---|---|---|
| `organizations` | компании/сотрудники | не вызывает ML |
| `calls` | метаданные, upload, storage | не запускает ASR внутри HTTP |
| `jobs` | durable lifecycle и leases | не содержит domain scoring |
| `transcription` | ASR adapter / canonical transcript | не знает UI |
| `analysis` | LLM adapter, evidence validation | не пишет raw-результат напрямую в отчёты |
| `scorecards` | версия чек-листа + чистый scorer | без IO и LLM |
| `reporting` | SQL aggregates | не вызывает модели |

## Happy path

1. UI `POST /api/v1/companies/{id}/calls` с multipart + `Idempotency-Key` (после server-side validation).
2. API потоково записывает файл в временное хранилище, проверяет размер, MIME по содержимому, ffprobe-длительность и хеш; атомарно перемещает в приватную папку.
3. PostgreSQL получает `call`, `processing_run`, `job(state=queued)`; HTTP 202 возвращает `call_id` и `run_id`.
4. Worker забирает задачу из PostgreSQL (`FOR UPDATE SKIP LOCKED`) и арендует её `lease_expires_at`.
5. Worker открывает аудио → ASR → создаёт immutable версию transcript → LLM → нормализует output → валидирует evidence → сервер вычисляет score → сохраняет immutable analysis run.
6. Worker отмечает `completed`; UI делает polling статуса; карточка получает транскрипт и аналитику.
7. Отчёты строятся SQL-запросами из опубликованных `completed` анализов.

## Стейты и восстановление

```
queued → processing → completed
                  ↘ retry_wait → queued
                  ↘ failed
```

`stage` принимает `preprocess`, `transcribe`, `analyze`, `validate`, `publish`. При перезапуске worker проверяет истёкшую аренду; повторяемые операции должны быть идемпотентны, иначе дубль анализа. Опубликовать `completed` можно **только** после транзакционной записи validated анализа.

## Интерфейсы, не реализации

- `Storage`: `put`, `open`, `delete`, `stat` → V0 `LocalStorage`, потом S3.
- `ASRProvider`: `transcribe(audio_asset, settings) -> CanonicalTranscript` → `MockASR`, `FasterWhisperASR`, future `CloudASR`.
- `LLMProvider`: `analyze(transcript, scorecard, taxonomy) -> AnalysisCandidate` → `MockLLM`, `OllamaLLM`, future external API.
- `TaskLeaseRepository`: DB-only; не привязывать домен к Celery.
- `Clock` и `UUID` inject for deterministic tests.

## Почему не микросервисы прямо сейчас

Один разработчик иначе получит сетевые сбои, распределённые трассы, отдельную авторизацию каждого сервиса, сложный CI и высокую стоимость сопровождения раньше, чем увидит пользу продукта. **Правила микросервисов (автономные границы, контракты, retries, observability, никакой shared mutable state) используются в модулях уже сейчас**, но физическое разделение откладывается.

## Моменты для разделения

- Длительный inference блокирует масштабирование worker → выделить inference service / GPU worker.
- Разные команды / независимые релизные циклы и стабильные контракты → возможное разделение сервисов.
- Большие объёмы и требования к независимой отказоустойчивости → брокер и специализированные storage.
- До этих событий: PostgreSQL + один worker достаточны при тестовой нагрузке.



---

# 03. Локальная разработка, ОС, зависимости и runbook

## Рекомендуемая машина

Windows 11 + WSL2 Ubuntu, VS Code Remote WSL, Git, Docker Desktop с WSL2 integration. Исходники в `/home/<username>/projects/voice-analytics`, не в `/mnt/c/...`. Для FastAPI, React, PostgreSQL и mock провайдеров **16 GB RAM достаточно при аккуратной настройке**. 32 GB комфортнее. GPU необязателен. На нестабильном ноутбуке допускается удалённая Ubuntu VM, подключение через SSH — не требуется для начала.

## Что установить

- WSL2/Ubuntu, Git, Docker Engine/Compose через Docker Desktop, Python 3.12 + `uv`, Node.js LTS + `pnpm`, `ffmpeg/ffprobe`, VS Code.
- Опционально Ollama для `qwen3:4b` (проверить свободную RAM; уменьшить контекст/параллелизм).
- Опционально `faster-whisper` для CPU INT8; первая загрузка весов требует интернет и свободное место.

## Предлагаемая структура

```
voice-analytics/
  AGENTS.md                   # правила coding-агентов
  README.md
  docs/ adrs/ contracts/
  apps/
    api/                     # FastAPI app, routes, persistence, Alembic
    worker/                  # polling DB tasks + pipelines
    web/                     # React/Vite/TypeScript
  packages/
    core/                    # чистые Pydantic схемы и бизнес-правила
    ai_adapters/             # mock/faster_whisper/ollama
  infra/
    compose.yaml             # PostgreSQL, опционально Ollama
  data/                      # локальные аудио; gitignored, не использовать для ПДн
  tests/fixtures/            # маленькие искусственные данные
  scripts/                   # seed demo, smoke, eval
  .github/workflows/ci.yml
```

## Предполагаемые команды ПОСЛЕ реализации (не готовые скрипты)

```bash
cp .env.example .env
# Установить uv и pnpm; выбрать mock-провайдеры

docker compose -f infra/compose.yaml up -d db
uv sync
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
# отдельный терминал:
uv run python -m apps.worker
# отдельный терминал:
cd apps/web && pnpm install && pnpm dev --host 127.0.0.1
```

**Важно:** эти команды являются ЦЕЛЕВЫМ интерфейсом будущего репозитория. Документация не утверждает, что сейчас существует запускаемый код. Агент обязан реализовать и проверить эти команды в Phase 0.

## Профили провайдеров

- `PROFILE=mock` — для быстрого демо и CI; все Mock результаты маркированы.
- `PROFILE=local_models` — faster-whisper на CPU, Ollama (лучше запускать по очереди на 16 GB RAM).
- `PROFILE=hybrid` — один/оба шага внешним API (ТОЛЬКО с разрешёнными тестовыми данными; credentials в env, не в Git).

## Лимиты для ноутбука

Worker concurrency=1; максимальный размер файла/длительность настраиваются; Ollama модель можно выключать между тестами; не запускать несколько тяжёлых inference одновременно; CPU ASR может быть медленным. Проверить Docker disk usage, память WSL, данные в `.gitignore`.

## Цикл изменения

`branch → 1 task → tests → lint/typecheck → manual smoke → PR/merge`. Для одиночного разработчика PR можно использовать как self-review; CI должен фиксировать не только успешное создание контейнера, но и отрицательные тесты.



---

# 04. Модель данных PostgreSQL для V0

## Сущности и обязательные поля

| Таблица | Поля | Ограничения |
|---|---|---|
| `companies` | id UUID PK, name, created_at | имя в пределах demo, unique не обязателен |
| `employees` | id UUID PK, company_id FK, display_name | FK и индекс company_id |
| `calls` | id UUID PK, company_id FK, employee_id nullable FK, filename_safe, object_key, audio_sha256, duration_ms, status, created_at, idempotency_key | unique(company_id,idempotency_key) для непустых ключей; employee только из этой company |
| `processing_runs` | id UUID PK, call_id FK, stage, status, attempt, lease_until, started_at, completed_at, failure_code, created_at | индекс status/lease_until, immutable provider settings snapshot |
| `transcripts` | id UUID PK, run_id FK unique, schema_version, asr_provider, asr_model, payload_jsonb, created_at | immutable; validated segment schema |
| `analysis_runs` | id UUID PK, run_id FK unique, transcript_id FK, scorecard_version, taxonomy_version, llm_provider, llm_model, prompt_version, is_mock, payload_jsonb, created_at | immutable после публикации |
| `scorecards` | id UUID PK, company_id FK, version, active, config_jsonb | unique(company_id,version) |
| `call_events` | id UUID PK, call_id FK, run_id FK, event_type, occurred_at, metadata_safe_jsonb | no raw transcript / PII в payload |

Старые примеры `speaker_role` могут быть `unknown`: это валидное состояние. `run_id` связывает конкретные ASR и LLM версии. Повторный анализ создаёт **новый** `processing_run` и новый результат, не перетирает историю.

## Канонический транскрипт

`schema_version`, `call_id`, `transcript_id`, `run_id`, `audio_sha256`, `duration_ms`, `language`, `asr_provider`, `model_id`, `is_mock`, `segments[]`. Каждый сегмент: `segment_id`, `start_ms`, `end_ms`, `text`, `speaker_id?`, `speaker_role ∈ {manager,customer,unknown}`. При неизвестной роли в `speaker_id` можно оставить идентификатор без семантической роли.

Инварианты: `0 <= start_ms < end_ms <= duration_ms+epsilon`, уникальность `segment_id` внутри версии, текст ограничен по длине, сегменты в отсортированном порядке (перекрытия допускаются при явном флаге/диаризации), no hallucinated evidence. `segments` никогда не редактируются после публикации.

## Результат анализа

`topic_code`, `outcome_code`, `objections[]`, `reasons[]`, `criterion_results[]`, `score`, `coverage`, `provider`, `model_id`, `prompt_version`, `scorecard_version`, `is_mock`. `criterion_results`: `{criterion_key, status, evidence_segment_ids, explanation, support}` с `status ∈ {pass, fail, unknown, not_applicable}`. `support ∈ {supported, insufficient_evidence, disputed}`.

## Formula score

\[S=100\cdot\frac{\sum_{i \in A, status_i=pass} w_i}{\sum_{i \in A}w_i}\]

где `A` — критерии с `pass` или `fail`, **исключая** `unknown` и `not_applicable`. Если знаменатель ноль, `score=null`. Отдельно хранить `coverage=сумма оценённых весов / сумма весов всех применимых и неопределённых` (для V0 явно описать политику N/A). Score не выдаёт LLM как источник истины.

## Файловое хранилище

В PostgreSQL только ключ файла и метаданные. Файлы физически `data/audio/<company_uuid>/<call_uuid>/original.<validated_ext>`. Не хранить исходное имя как путь. `data/` за пределами git и с правами, ограничивающими доступ; не отдавать directory listing. Удаление звонка для V0 очищает SQL и файл; ошибки удаления объектов должны быть видны в логах/админ-команде. Синхронизировать физические файлы и БД, расследовать orphan files.

## Миграции

Только Alembic, без автосоздания таблиц на старте API; schema tests проверяют FK/unique/check и downgrade (когда безопасно). До реализации записать `EXPLAIN` для dashboard queries при >10k звонков — пока не нужен ClickHouse.



---

# 05. REST API контракт для локального прототипа

**База:** `/api/v1`; локально `http://127.0.0.1:8000`. Данные передаются JSON кроме аудиозагрузки. Swagger/OpenAPI генерируется из FastAPI и сверяется с `contracts/openapi.yaml` (файл — проектный черновик). Все UUID — строковые UUID. `demo-company` переключатель допустим **только на localhost**.

## Endpoints (V0)

| Метод | Путь | Назначение / пример статуса |
|---|---|---|
| GET | `/health/live` | проверка процесса, 200 |
| GET | `/health/ready` | проверка БД, 200/503 |
| POST | `/companies` | создать test-company, 201 |
| GET | `/companies` | список компаний, 200 |
| POST | `/companies/{company_id}/employees` | создать сотрудника, 201 |
| GET | `/companies/{company_id}/employees` | список сотрудников, 200 |
| POST | `/companies/{company_id}/calls` | multipart `file`, `employee_id?`, header `Idempotency-Key`, 202 |
| GET | `/companies/{company_id}/calls` | пагинация, фильтр статуса/employee, 200 |
| GET | `/companies/{company_id}/calls/{call_id}` | данные звонка + активный run, 200/404 |
| GET | `/companies/{company_id}/calls/{call_id}/audio` | защищённый *локальным режимом* stream/Range, 200/206 |
| GET | `/companies/{company_id}/calls/{call_id}/transcript` | сегменты или 409 до готовности |
| GET | `/companies/{company_id}/calls/{call_id}/analysis` | структурированный результат или 409 |
| GET | `/companies/{company_id}/dashboard` | агрегация completed, 200 |
| POST | `/companies/{company_id}/calls/{call_id}/retry` | ручной рестарт по policy, 202 |
| DELETE | `/companies/{company_id}/calls/{call_id}` | удалить demo call и файлы, 204 |

Ответ `POST /calls`:

```json
{"call_id":"<uuid>","run_id":"<uuid>","status":"queued","is_mock":true}
```

Ответ ошибки:

```json
{"error":{"code":"UNSUPPORTED_AUDIO","message":"Формат аудио не поддерживается","request_id":"<uuid>"}}
```

## Семантика

- Все ресурсы ищутся *в рамках* `company_id`; 404 если `call` иной компании (это базовая защита ошибок, не production auth).
- Для повторного `Idempotency-Key` + того же содержимого возвращать существующий `call_id`; **тот же ключ с другим SHA256 → 409**. TTL ключа V0 не нужен или задаётся явно.
- API не ждёт ASR/LLM (долгая операция). В status endpoint сообщение `queued|processing|completed|failed`, stage, progress только если есть реальный сигнал.
- `retry`: failed/expired выполняются без создания дубликатов published результата; новое осознанное переанализирование с другой конфигурацией — отдельный run.
- Максимальный upload и время обрабатываются явно: 413, 415, 422, 429 (если добавлен limit), 503. При падении `ffprobe` файл не публикуется.
- Все выборки `limit/offset` или cursor, сортировка стабильна; запрет доступа к файлу по произвольному `path` из запроса.

## Будущая интеграция

CRM/webhooks, публичный presigned-upload, OAuth, API keys и разделение auth scopes **не входят в V0**. Создание этих endpoints потребует отдельных ADR и security review. Нельзя использовать demo header / company_id как доказательство авторизации в сети.



---

# 06. Модельный pipeline: предобученные модели без fine-tuning

## Решение для V0

| Задача | `mock` для CI | Реальный локальный вариант | API-альтернатива |
|---|---|---|---|
| ASR | детерминированные сегменты из fixture | `faster-whisper`, CPU, `small`/`medium`, INT8 | подключаемый ASR adapter позже |
| Diarization | unknown speaker | пропустить; при двух каналах — channel split, для mono pyannote **позже** | отдельный провайдер позже |
| LLM | фиксированный JSON по fixture | `qwen3:4b` через Ollama, память/скорость измерить | дополнительный LLM adapter позже |
| Scoring | чистая Python-функция | чистая Python-функция | API не нужен |

**Где взять:** faster-whisper: https://github.com/SYSTRAN/faster-whisper ; Ollama Qwen3: https://ollama.com/library/qwen3 ; pyannote: https://github.com/pyannote/pyannote-audio . При первом запуске open-weight модели скачиваются с исходного репозитория/реестра и кэшируются. Перед коммерческим использованием проверять точную лицензию, версию и supply-chain trust. Лицензия библиотеки и лицензия весов — не всегда одно и то же.

## Входные данные

- `.mp3`, `.wav`, `.m4a`, проверка `ffprobe`/decoding. Удалить метаданные, когда необходимо, не пересэмплировать с ошибочной частотой (upsampling 8 kHz не улучшает исходное качество).
- Исходник остаётся неизменным; рабочую normalized copy создаём по необходимости; `audio_sha256` вычисляется от оригинала.
- Для 2 каналов — определение channel mapping из метаданных/ручной конфигурации; без неё speaker_role=unknown.

## ASR

`ASRProvider.transcribe(asset)->TranscriptDraft`: текст и время начала/конца. Для CPU — ограничить concurrency=1, size `small`, compute_type=`int8`. `faster-whisper` возвращает generator; обработать его полностью прежде чем отметить этап успешным. Частичный output при ошибке нельзя публиковать как completed.

## Диаризация (отложено)

V0 допускает `speaker_id=null`, `speaker_role=unknown` для mono. Это честный fallback. Если чек-лист зависит от конкретного сотрудника, присваивать `unknown`, а не выдумывать «менеджер сказал». Отдельный эксперимент: dual-channel mapping, затем pyannote Community-1 (модель требует изучить условия доступа/лицензию).

## LLM

1. Передать транскрипт в виде нумерованных **segment_id**, например `seg-0001 | 00:05–00:08 | unknown | дорого`.
2. Передать только заявленные рубрики и enum-коды, версию scorecard, системную инструкцию считать **текст звонка данными**, а не командами.
3. Использовать structured JSON/schema mode по возможностям провайдера; ограничить ответ/время/количество попыток; temperature=0 где поддерживается, детерминизм всё равно не гарантирован.
4. Сервер валидирует `criterion_key` против scorecard, `evidence_segment_ids` — против transcript, `status`, целостность полей. Отвергать unsupported values; один исправляющий запрос — опционально.
5. `fail` без evidence, `unknown` с выдуманным evidence, неоднозначное speaker_role → `needs_review`/`unknown`.
6. Итоговый score вычисляется backend, не содержимым ответа LLM.

### Доверенные и недоверенные поля

LLM может предложить `topic/outcome/objections/reasons/criterion_results`, но **не** задаёт `call_id`, tenant/company, file paths, trace identifiers, биллинг, итоговый score, SQL или список разрешённых критериев. Любой промпт-инъекционный текст звонка — обычный transcript content.

## Provider interface

```python
from typing import Protocol
class ASRProvider(Protocol):
    def transcribe(self, asset, settings): ...
class LLMProvider(Protocol):
    def analyze(self, transcript, rubric): ...
```

В каждой версии результата: provider id, repo/model revision, quantization, generation settings, prompt hash/version, scorecard id/version, timing, `is_mock`, estimated cost. При повторном inference создаётся новая analysis run.

## Активация поэтапно

1. Mock→Mock: быстрее всего проверить продукт целиком.
2. `faster-whisper`→Mock: проверить реальные таймкоды и обработку ошибок.
3. `faster-whisper`→Ollama Qwen: реальный end-to-end inference.
4. Опционально подключить более сильный hosted LLM для сравнений на **разрешённых данных**. Не превращать зарубежные API в скрытую production-зависимость.
5. Диаризация, fine-tuning, GPU — только если baseline показал необходимость.

## Ключевые риски

ASR галлюцинирует на тишине, путает отрицания и числа; роль говорящего неизвестна; Qwen 4B может ошибаться в сложных рубриках и JSON; CPU inference медленный; краткие сегменты не совпадают с фразами, поэтому reviewer должен оценивать семантику evidence, а не только existence ссылок.



---

# 07. Тестирование ML и минимальный MLOps для V0

## Мы не тренируем свои модели, но MLOps всё равно нужен

- Воспроизводимость: фиксировать версии весов и входных файлов, ASR/LLM параметры, версии prompt/schema/scorecard.
- Data quality: входные медиа, длительность, каналы, пустая/неразборчивая речь, ошибки языка.
- Model quality: отдельно оценивать ASR и бизнес-выводы LLM.
- Model release: кандидаты сравниваются на фиксированном разрешённом evaluation set; регрессия блокирует обновление.
- Monitoring: latency, failures, errors, доли `unknown`, schema-valid %, evidence-valid %, стоимость/мин.

## Датасеты

`tests/fixtures/` — только искусственные или специально разрешённые маленькие записи, хеши и reference transcripts. `evaluation/private/` (gitignored, encrypted when needed) — позже реальные записи по оформленному основанию. В JSONL annotations: call_id, reference text, speaker role if known, topic, outcome, objections, criterion labels, evidence IDs/intervals и annotator. Не публиковать raw ПДн в Git/CI/облачных агентах.

## Метрики и what can go wrong

| Метрика | Как считать | Важное ограничение |
|---|---|---|
| WER / CER | сравнить с ручным транскриптом | нужны правила нормализации чисел/пунктуации |
| Speaker role accuracy | точность role attribution | только на звонках с gold labels |
| Topic/outcome macro-F1 | по human-annotated calls | учитывать редкие классы и unknown |
| Criterion F1 / error count | по каждому чек-листу | false accusation («менеджер нарушил») критична |
| Evidence existence | % segment_ids из transcript | необходимое, но недостаточное условие |
| Evidence relevance | люди оценивают объяснение | автоматически полностью не проверить |
| Coverage | доля оценимых критериев | `unknown` не маскировать |
| Latency / RTF | обработка звонка по минутам | тестировать на той же машине/конфигурации |
| Unit cost | расход ресурса на 1 минуту | локальное оборудование/электроэнергия тоже стоимость |

## Минимум до первой демо-демонстрации

- 5–10 коротких фикстур для контрактов / end-to-end состояния; 10–20 отдельно размеченных тестовых звонков — **ориентир для сравнения**, не доказательство industrial quality.
- Скрипт `scripts/evaluate.py`: json report с каждым провайдером, версиями, метриками и датой; никакой публичной accuracy-процентной рекламы по маленькой выборке.
- Контрольное обновление prompt: regression cases по `unknown`, `not_applicable`, пропущенным критериям, фиктивным `segment_id`, injection тексту.
- Проверка, что UI различает mock/real и ошибки, а не показывает пустые данные как успех.

## Релиз модели / промпта

1. `candidate` с зафиксированными hash/version.
2. offline eval на неизменной выборке.
3. compare vs baseline, запись `docs/decisions/` или ADR.
4. ручная проверка примеров с худшими ошибками.
5. заменить default adapter/config, оставить rollback.
6. новая обработка создаёт новый run. Старый вывод не перезаписывается.

## Дообучение — LATER

Fine-tuning/LoRA рассматривается только при достаточном **разрешённом** размеченном корпусе, устойчивой проблеме после prompt/правил и положительном trade-off cost/quality. Не использовать продакшен-звонки как обучающий корпус по умолчанию.



---

# 08. Надёжность, error handling и SRE без избыточной инфраструктуры

## Ключевой инвариант

Система может выполнить один этап более одного раза после crash/retry (**at-least-once**), но должна создавать **не более одного опубликованного результата на `run_id`**. Не обещать exactly-once execution.

## DB worker без Redis

- `processing_runs` с `status`, `stage`, `attempt`, `lease_until`, `last_error_code`.
- Worker запрашивает очередную запись транзакционно с `SELECT ... FOR UPDATE SKIP LOCKED` и ставит lease; затем выполняет работу **вне** DB-транзакции.
- Длительный этап должен продлевать lease heartbeat, либо lease duration рассчитывается с запасом и при краше корректно обрабатывается. Маленький polling interval с backoff.
- Для истекшего lease — requeue, если `attempt < max_attempts`, иначе `failed` с безопасной ошибкой. `max_attempts` по умолчанию 3.
- Каждый дорогой этап записывает checkpoint и bounded output; retry не размножает versions и не публикует partial output.
- В одном worker instance concurrency 1; по умолчанию нет горизонтального масштабирования до нагрузочных испытаний.

## Классификация ошибок

| Ошибка | Действие |
|---|---|
| Unsupported/corrupt audio | permanent failed, retry бесполезен |
| ASR provider unavailable / 429 / transient IO | bounded retry с exponential backoff + jitter |
| OOM в Ollama | failed и явная рекомендация уменьшить модель; без бесконечного restart |
| LLM invalid JSON | максимум 1 schema repair, затем failed или needs_review |
| Evidence out of transcript | не публиковать `supported`, перевод в unknown/review |
| Worker killed | lease recovery, повтор idempotent |
| PostgreSQL unavailable | readiness=false, worker wait/backoff, не потерять job |

## Observability

Логи в JSON (timestamp, request_id, company_id, call_id, run_id, stage, elapsed_ms, error_code), **без содержимого аудио/транскрипта и секретов**. Для первой версии достаточно Prometheus metrics или JSON logs + локальный монитор ошибок. OpenTelemetry/trace collector — LATER. Endpoint `/health/live` проверяет процесс, `/health/ready` БД, опционально disk space.

Метрики: queued count, oldest queued age, processing count, failed count, completion ratio, stage latency, schema_invalid, evidence_invalid, mock/real counts, duration processed. Сначала наблюдаемость для диагностики, не формальные production SLO.

## Тесты с инъекцией отказов

1. Один и тот же upload idempotency key дважды → одна запись.
2. Kill worker между ASR и LLM → restart → completed или explicit failed; не 2 analysis rows.
3. LLM вернул неверный segment ID → не completed supported.
4. Загрузка повреждённого файла → 4xx/failed, temporary file убран.
5. PostgreSQL down → понятная ошибка и отсутствие потери подтверждённых jobs.
6. Время на inference истекло → ограниченный retry и final state.

## Когда понадобится брокер

При увеличении throughput, необходимости более строгой доставки/маршрутизации и независимых worker pools. Тогда сравнить Redis/Celery, RabbitMQ и Temporal с учётом затрат; domain processing state уже не зависит от брокера.



---

# 09. Безопасность и конфиденциальность: граница локального демо

## Для V0: только локально

**V0 нельзя подключать к публичному интернету и использовать для обработки чужих реальных разговоров.** В проекте пока нет production-grade auth, tenant authorization, шифрования и процедур персональных данных. Создание двух компаний внутри демо — UX и схема БД, но не фактическая изоляция коммерческих клиентов.

- Привязать dev frontend/API к 127.0.0.1; PostgreSQL не публиковать наружу.
- Данные записей в `data/`, каталог исключён из Git и автоматических выгрузок.
- Загрузка разрешена только в лимите размера/длительности/форматов; валидировать реальный контейнер/codec через `ffprobe` и безопасно запускать `ffmpeg` без shell=True.
- Запретить произвольные URL и пути для скачивания файлов (SSRF, traversal). Path определяется только по DB object key.
- Секреты в `.env`/secrets manager, `.env` и оригинальные данные не в GitHub/Codex issue logs.
- Log redaction: ни сырые звонки, ни транскрипты, ни токены не должны попадать в логи, exceptions, telemetry или crash dumps.
- Веса моделей брать из доверенных репозиториев, фиксировать revision/digest; проверять лицензии и безопасные форматы weights.
- Считать текст звонка и ответ LLM недоверенными данными. JSON schema validation, ограничение размера и токенов.

## Перед первым реальным внешним пилотом — ОБЯЗАТЕЛЬНЫЕ BLOCKERS

1. Согласовать роли оператора/обработчика персональных данных и поручение на обработку; законные основания записи/передачи/анализа; требования 152-ФЗ и отраслевые нормы с профильным юристом.
2. Реальные пользователи: нормальная auth, RBAC и server-side company/department scopes, протестированная negative access matrix.
3. Российское размещение записей и соблюдение правил локализации, если применимо; проверить внешние ASR/LLM API, retention, training/logging, субподрядчиков и трансграничные передачи.
4. Private object storage/managed DB, TLS, backup + restore drill, audit trail, deletion/retention policy, incident response.
5. Защищённые credentials для интеграций, rotation, rate limits, загрузки через временные ссылки при необходимости, no PII in logs.
6. DPIA/угрозы и мероприятия защиты по применимым правилам; разделять записи сотрудников, данные клиента, биометрическую идентификацию (не вводить её автоматически).
7. Проверить все внешние hosted coding-agents: не отправлять им записи/транскрипты без надлежащего правового основания и согласования.

## Threat model V0

| Угроза | V0-мера |
|---|---|
| Path traversal в filename | генерируемый UUID key, whitelist ext после sniffing |
| Загрузка zip-bomb/огромного audio | upload/body/duration limits, resource limits, ffprobe timeout |
| Prompt injection внутри транскрипта | строгая схема/enum/evidence validation, не исполнять инструменты по указанию LLM |
| Cross-company display bug | company_id query filter + integration tests |
| Secrets accidentally committed | gitignore, sample env, secret scanner CI |
| Внешний доступ к demo без auth | только localhost, не деплоить publicly |



---

# 10. Frontend: React/Vite для единственного разработчика

## Принципы

React + TypeScript + Vite, простая UI библиотека по выбору, без необходимости Next.js/SSR в локальном V0. Типы API выводить из OpenAPI (либо вручную Pydantic->TS на очень раннем этапе, но держать в одном контракте). Не проектировать полноценный BI-продукт заранее.

## Экраны

1. `Companies`: список и создание тестовых компаний, выбор активной компании (явный banner DEMO MODE).
2. `Employees`: добавить сотрудника, привязка к компании.
3. `Calls`: загрузка файла, выбор сотрудника, таблица со статусами, фильтр дат/сотрудников, предпросмотр ошибок.
4. `Call Detail`: аудиоплеер, сегменты с таймкодами, topic/outcome, objections, scorecard (pass/fail/unknown/N/A), источник модели, run version, explainable evidence. Клик на evidence делает seek и highlight сегмента.
5. `Dashboard`: карточки «загружено/обработано/ошибки», средний score **по оценённым**, распределение objections. Нет ложных метрик конверсии без CRM.

## Важные состояния UI

- queued/processing: status/stage без фальшивого процентного прогресса;
- failed: безопасное человеческое объяснение + retry;
- completed/mock: яркая текстовая пометка `ДЕМО-РЕЗУЛЬТАТ`; completed/real: точная модель/версия;
- unassigned speaker: speaker_0/unknown, без имени менеджера в выводе;
- unsupported/unknown: отдельное состояние, не красный «провал»;
- пустой dashboard: «Нет обработанных звонков» вместо нулевых маркетинговых KPI.

## Тесты

E2E через Playwright: create company → employee → upload fixture → mock result → click evidence → player currentTime → switch company → no previous company's calls. Это тест поведения UI, а не доказательство production авторизации.



---

# 11. План разработки в одиночку: incremental vertical slices

**Правило:** завершённым считается только этап, у которого есть working demo, тесты, документация и воспроизводимые команды запуска. Этапы не равны неделям; конкретные сроки зависят от оборудования и рабочего времени.

| Этап | Содержимое | Acceptance / Definition of Done |
|---|---|---|
| V0-00 Bootstrap | monorepo, `uv`, TS/Vite, Docker Compose db, Ruff/pytest, pre-commit, CI | `make test`/эквивалент в CI green; health/live/ready |
| V0-01 Домен | компании, сотрудники, migrations, seed; local demo mode | 2 company seeds, company filter tests, schema migration |
| V0-02 Upload & job | upload, ffprobe, local storage, SQL job, worker | 202; 4xx для bad audio; повтор запроса не дублирует; kill/restart test |
| V0-03 Mock full slice | mock transcript + analysis + scorer, API call detail | 1 тестовый звонок показан end-to-end с mock labels |
| V0-04 Real ASR | faster-whisper CPU adapter + timings/model metadata | на разрешённом WAV реальный transcript; error handling, model version |
| V0-05 Real LLM | Ollama Qwen adapter + schema/evidence validation | локальный model call, невалидный JSON/segment тестируется |
| V0-06 Frontend | companies/employee/calls/detail/player | Playwright smoke, no stale data when switching company |
| V0-07 Dashboard | topic/outcome/objections, average score SQL | агрегаты совпадают с fixtures, разные компании не смешаны |
| V0-08 Reliability & eval | benchmark script, retry/lease, logs, docs, CPU timings | тесты crash/retry; report WER & business-label eval; no PII in logs |

## Текущий MVP DONE

1. `README.md` даёт точную проверенную последовательность локального старта.
2. Все HTTP endpoints из V0 реализованы и документированы.
3. 2 компании / 2 сотрудника / 3 файла воспроизводимо импортируются.
4. Mock работает без сети, реальный ASR/LLM работает при подходящих ресурсах.
5. Пользователь видит непротиворечивый результат, evidence click, missing speaker roles отображаются как unknown.
6. Любой сбой приводит к явному status; после рестарта подтверждённые jobs не теряются.
7. Чек-листы версионированы, scoring deterministic, stale run не затирается.
8. Unit/integration/E2E + quality-report скрипт, нет известных критических дыр при **локальном** запуске.

## Что НЕ делать прежде V0 DONE

Kubernetes, Kafka, ClickHouse, полнофункциональная CRM-коннекторная система, public multi-tenant auth, админ-панель провайдеров, SaaS billing, RAG, сложная online-диаризация, fine-tune, красивый маркетинговый сайт.

## Переход к реальному пилоту

Сначала получить конкретную компанию и legal approval; затем `[P1-01] auth/RBAC & multitenant tests`, `[P1-02] secure object store & real hosting`, `[P1-03] first telephony connector`, `[P1-04] observability/backups/retention`, `[P1-05] human rubric calibration`. Их detailed blueprint оставлен в `reference/legacy-v0.1/`.



---

# 12. Codex / Claude Code — протокол разработки без хаоса

## Workflow

1. Каждый запрос = одна задача из `docs/11-implementation-plan.md`, номер `V0-XX` + шаг; сначала попросить план, список файлов и тестов.
2. Агент обязан читать `README.md`, `AGENTS.md`, relevant docs, `adrs/`, `contracts/`; **не использовать** `reference/legacy-v0.1/` как текущие требования.
3. В каждом PR: выполняемый код, тесты (happy + negative), migrations (если DB), обновление README/contract, команды/вывод тестов.
4. Переходить дальше только после локального запуска / воспроизводимого теста, не писать весь продукт одним запросом.
5. Новые библиотеки/контейнеры/сервисы и изменение публичного API — только с краткой ADR и обоснованием.
6. Агенту запрещено утверждать, что он запустил модель/тест, если этого не было; mock всегда явно подписан.

## Первый task prompt — можно копировать

```text
Ты senior Python/full-stack engineer. Репозиторий: Voice Analytics V0.
Прочитай README.md, AGENTS.md, docs/01-product-scope.md,
docs/02-architecture.md, docs/03-local-development.md,
docs/11-implementation-plan.md и adrs/.

Выполни ТОЛЬКО задачу V0-00 Bootstrap.

Требования:
- Не добавляй Redis/Celery/Kafka/Kubernetes/S3/GPU и никаких CRM-коннекторов.
- Backend FastAPI, PostgreSQL через Docker Compose,
  frontend React/Vite, Python uv, lint/test/CI.
- Прежде кода перечисли файлы, команды запуска и acceptance tests.
- Напиши минимальный проверяемый scaffold с health/live и health/ready.
- Реальные модели пока НЕ запускай; не выдавай mock за реальный inference.
- Затем выполни тесты и укажи команды, exit code, ограничения.
```

## Шаблон для следующих задач

```text
Задача: V0-XX / <конкретный acceptance item>.
Обязательные источники: README.md, AGENTS.md, docs/XX, contracts/XX.
Работай в одной ветке, меняй только затронутые модули.
Сначала изложи data flow, инварианты, план миграций, тесты.
Реализуй минимально; проведи unit/integration/negative тесты.
Не меняй ADR и API молча. Не загружай реальные записи во внешние сервисы.
В конце: список diff, команды, наблюдаемые результаты, остаточные риски.
```

## Чек-лист человека

- [ ] Работает ли основной сценарий сам, а не только в мок-тесте?
- [ ] Проверяется ли путь «неправильные данные»?
- [ ] Нет ли скрытых дополнительных сервисов и сложного абстрактного framework?
- [ ] Запись `queued` не теряется и `completed` не дублируется?
- [ ] Нет ли выдуманных evidence, speaker roles, scores или mocked success?
- [ ] Данные компаний не смешиваются даже в демо?
- [ ] В логах, Git, CI нет аудио/транскриптов/ключей?
- [ ] Код покрыт тестами и команды соответствуют README?



---

# 13. Переход V0 → Pilot SaaS: критерии, а не обязательный backlog

Сначала доказать, что локальная система качественно анализирует звонки и что хотя бы одной компании это нужно. Потом решать, как обрабатывать настоящие записи.

## Pilot gates

- Компания-клиент, способ получения разрешённых звонков, бизнес-рубрика и эксперт для оценки.
- Поручение/соглашение об обработке персональных данных, размещение, retention и провайдеры согласованы.
- Перейти с локальных файлов на приватный S3-compatible storage; back-ups/restore и delete lifecycle.
- Настоящая авторизация (OIDC или equivalent), проверки tenant scopes в каждом эндпоинте, audit.
- Один внешний provider интеграции, event/webhook dedup, backfill, reconciliation.
- Надёжная очередь при измеренной нагрузке, monitoring/alerts, developer runbooks, обоснованные SLO.
- UI для human review и спорных оценок; validation benchmark на реальных разрешённых данных.
- Оценить API-vs-GPU unit economics, нагрузочное тестирование и доступность нужных регионов.

## Необходимость микросервисов решается фактами

Отдельный inference deployment обоснован, когда GPU/concurrency/resources сильно отличаются от web/backend; отдельный ingest service — если количество интеграций и частота изменений достаточны; billing — после подписанной коммерческой модели; выделение нескольких сервисов не является требованием зрелости продукта.

## Архитектурная эволюция

```
V0 local:            API + worker + PostgreSQL + local files
Pilot SaaS:          API + worker + managed PostgreSQL + S3 + real auth + observability
Growth (if needed):  API + ingest worker + inference worker + queue + separate scaling
Enterprise option:   isolated deployments / on-prem after specific contractual demand
```

Сохранён исходный документ на пилот в `reference/legacy-v0.1/old-full-spec.md`, но при конфликте приоритет имеют текущие документы V0.2.



---

# 14. Рынок и реальные архитектурные ориентиры (сохранено из v0.1)

Этот раздел **не является спецификацией для первой разработки**. Исследование международных/российских продуктов, выполненное 02.11.2026, находится в `reference/legacy-v0.1/market-landscape.md`. См. документы источников в `docs/15-sources.md`.

## Что переносим в продукт позже

| Источник | Публично описанная продуктовая/техническая практика | Наше решение |
|---|---|---|
| SalesAI | Pipeline API/Platform API, upload через presigned URL, async jobs | V0 сначала локальный upload + persistent job; S3 позже |
| MiaRec | workflow события → ASR → AI task → сохранение, очередь задач | Разделить stages, хранить состояние durable |
| Aircall | автоназначение критериев качества в зависимости от звонка | V0 фиксированная scorecard; rules routing позже |
| Gong | связь звонка с CRM/deal context | сделку добавить, когда будет CRM |
| Observe.AI / CallMiner | масштабируемый контроль качества, human workflows | версионирование, evidence, review после V0 |
| imot.io | вертикальные сценарии и CRM-enrichment | сначала проверить одну вертикаль |

Публичные заявления поставщиков не позволяют установить, какие конкретно брокеры/модели/базы данных работают внутри конкурентов. Никакие внутренние конфигурации не выдаются за факты.



---

# 15. Источники и оговорки

Дата базового обзора 02.11.2026. Ссылки здесь — для проверки проектных решений. Продуктовые страницы вендоров подтверждают **их заявления**, а не независимо проверенное качество.

## Инженерные источники

- FastAPI Background Tasks и предупреждение о тяжёлых задачах: https://fastapi.tiangolo.com/tutorial/background-tasks/
- faster-whisper, CPU/INT8, установка и примеры: https://github.com/SYSTRAN/faster-whisper
- Ollama Qwen3 модели и теги: https://ollama.com/library/qwen3
- pyannote Community-1 и speaker diarization: https://www.pyannote.ai/blog/community-1
- PostgreSQL locking / `SKIP LOCKED`: https://www.postgresql.org/docs/current/sql-select.html
- Docker Compose: https://docs.docker.com/compose/
- SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/orm/
- Alembic migrations: https://alembic.sqlalchemy.org/en/latest/
- OWASP API Security Top 10: https://owasp.org/API-Security/
- Google SRE Book: https://sre.google/books/
- ML technical debt: D. Sculley et al., Hidden Technical Debt in ML Systems (2015) https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html
- ML testing: E. Breck et al., What's Your ML Test Score? https://research.google/pubs/whats-your-ml-test-score-a-rubric-for-ml-production-systems/
- Rules of Machine Learning: https://developers.google.com/machine-learning/guides/rules-of-ml/

## Платформы (публичные сведения)

- SalesAI API: https://salesai.ru/docs/api-pipeline/
- MiaRec operator-guide pipeline: https://docs.miarec.com/operator-guide/conversation-analytics/pipeline-overview/
- Aircall automated scorecards: https://support.aircall.io/en-gb/articles/28736864368669
- imot.io: https://imot.io/developers
- Gong: https://www.gong.io/
- Observe.AI: https://www.observe.ai/
- CallMiner: https://callminer.com/
- Amazon Connect: https://docs.aws.amazon.com/connect/latest/adminguide/contact-lens.html

Расширенная таблица глобальных игроков и научных источников перенесена из v0.1 в `reference/legacy-v0.1/market-landscape.md` и `reference/legacy-v0.1/research-sources.md`. Версии моделей и цены провайдеров перепроверять непосредственно перед внедрением.



---

# 16. Принятые решения и нерешённые вопросы

## Зафиксировано

- Старт без реальной компании; только локальный demo environment.
- `companies` в базе нужны для проверки продукта, но не равны защищённой multi-tenancy.
- Не усложнять: DB job вместо брокера, локальный storage вместо S3, 1 worker, нет микросервисов.
- Один ASR adapter (faster-whisper) и один LLM adapter (Ollama/Qwen), mock counterparts для CI.
- Отсутствие диаризации в V0 допустимо; неизвестная роль не приписывается сотруднику.
- Сохранять версии ML-результатов и evidence, deterministic scoring.
- Реальные записи и внешние API запрещены без данных/правовых оснований.

## Решить по мере появления данных

1. Реальный целевой вертикальный рынок: недвижимость, колл-центры продаж, медицина, другое.
2. Будет ли ежедневный тест на ноутбуке с 16GB RAM или remote VM.
3. Достаточность CPU faster-whisper small/medium на собственных тестах.
4. Достаточность Qwen 4B vs более сильный API (accuracy и время).
5. Способ получать разрешённые audio/speaker labels и критерии экспертной оценки.
6. Когда переходить на полноценную диаризацию и какие language-specific качества нужны.
7. Нужна ли отдельная VM/GPU и какая российская облачная инфраструктура подходит под требования клиента.

## Принцип разрешения конфликтов

`README.md` и документы `docs/01`–`docs/13` **приоритетнее** `reference/legacy-v0.1/` для V0. Доработки оформляются ADR и корректировкой контрактов до написания кода.



---

# ADR-0001: Local-first V0 instead of production SaaS

**Status:** Accepted for V0.2 / 2026-11-02

Context: One developer, no pilot company, unstable/limited local hardware, product assumptions not validated.

Decision: local-only test companies, manual upload, modular monolith, DB-polling worker, local file storage, mock adapters with optional local real models. No external accessible auth or CRM.

Consequences: fast initial development; cannot deploy to real customers as-is. Need auth, S3, backup, compliance and integration before pilot.

Revisit if: first customer/pilot and legally permitted call data arrive.



---

# ADR-0002: PostgreSQL job queue instead of Celery/Redis for V0

**Status:** Accepted for V0.2 / 2026-11-02

Options: FastAPI BackgroundTasks (not durable), Celery+Redis (extra service), PostgreSQL stateful job queue (simple), Temporal (overkill). Choose DB queue with `FOR UPDATE SKIP LOCKED`, lease, bounded retry, idempotent publish. Never hold database transactions open while running ASR/LLM. Lease heartbeat or conservative safe lease TTL required.

Trade-offs: polling adds latency and limits scale; acceptable for one local worker. Revisit if multiple workers, throughput and orchestration complexity justify a broker.



---

# ADR-0003: Ready-made models with provider adapters

**Status:** Accepted for V0.2 / 2026-11-02

Baseline: MockASR & MockLLM in CI; optional real ASR=`faster-whisper` CPU INT8; LLM=`qwen3:4b` via Ollama; no required GPU or fine-tuning. `speaker_role=unknown` until verified audio channel assignment / diarization. All model output versioned. External APIs later behind contracts and data/legal gate.

Revisit: benchmark accuracy/latency/cost or model access/licensing changes.



---

# ADR-0004: Demo-only companies are not production multi-tenancy

**Status:** Accepted for V0.2 / 2026-11-02

No real external user authentication in V0. Company selector is a demo UX mechanism. All SQL queries are still scoped to company_id to prevent accidental mixing, but this is insufficient for Internet access. API binds to localhost; local Postgres is not published. Before a real pilot: authN/authZ, negative tests, legal framework, audit, encrypted storage, backups and hosting review.



---

# Instructions for coding agents — Voice Analytics V0.2

1. Current product is a LOCAL DEMO PROTOTYPE with one developer. Read `README.md`, `docs/01-product-scope.md`, `docs/02-architecture.md`, `docs/11-implementation-plan.md` before any code.
2. `reference/legacy-v0.1/` is historical background, NOT implementation requirements. Never implement its auth/billing/integrations by default.
3. Work on **one V0-XX milestone or narrower acceptance item**. Outline file changes, tests, and migration impact first. Implement narrowly.
4. No Redis, Celery, Kafka, Kubernetes, distributed services, mandatory S3, GPU or real CRM/telephony unless user explicitly approves a new ADR.
5. Use Python type hints, Pydantic domain/API schemas, migrations with Alembic, typed TS, deterministic scoring, dependency-injected adapters.
6. CI uses mocked providers only. Real ASR/LLM is optional manual smoke and must log provider/model/revision. Never call mock output real model output.
7. Strict `segment_id` evidence validation; `unknown`/`not_applicable` are NOT `fail`; score is calculated by deterministic code.
8. Acknowledged jobs must survive API/worker restarts. At-least-once processing, lease recovery, idempotent publish, bounded retry. No exactly-once claim.
9. Treat audio/transcripts as sensitive, even for demo. NEVER add real recordings, API keys, auth tokens, or transcripts to source/CI/issues/agent prompts.
10. Local demo has no production authentication; **NEVER expose it publicly** or claim it is safe for real customers.
11. Every completed change must include test commands, actual observed exit status and any unverified behaviour. Do not invent passing tests.
12. If a significant design decision changes, add an ADR. Maintain REST/OpenAPI and JSON schema contracts.



---

# Claude Code entry point

Read and obey `AGENTS.md`; it is authoritative. Start with `README.md`, then `docs/11-implementation-plan.md`. Use `docs/12-coding-agent.md` for task prompts. Build V0 milestone-by-milestone, not the whole SaaS at once. `reference/legacy-v0.1/` is reference-only.



---

# Чек-лист приёмки V0

- [ ] Локальный запуск API/worker/web/database документирован и проверен с чистого clone.
- [ ] Seed создаёт две вымышленные компании.
- [ ] Upload поддерживает допустимые файлы и блокирует 0-byte, oversized и corrupt fixtures.
- [ ] Повтор `Idempotency-Key` не создаёт второй call.
- [ ] Worker restart не теряет зарегистрированный job, publish не дублируется.
- [ ] Выбор mock/real виден в API и UI.
- [ ] Существующие evidence IDs валидны, выдуманные блокируются.
- [ ] Unknown и N/A не входят в score denominator.
- [ ] Speaker role unknown не превращается в manager/customer без основания.
- [ ] Реальный ASR и LLM проверены на разрешённых тестовых данных.
- [ ] E2E UI scenario работает, dashboard denominator проверен.
- [ ] В репозитории нет настоящих записей/секретов.
- [ ] Приложение доступно только локально, UI имеет Demo banner.
- [ ] Все README команды реально проверены и тестовые результаты сохранены.



---

# Пример локальной конфигурации (для будущего `.env.example`)

```dotenv
APP_ENV=development
BIND_HOST=127.0.0.1
POSTGRES_DSN=postgresql+psycopg://voice:local_dev_only@localhost:5432/voice_demo
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=./data/audio
MAX_UPLOAD_MB=50
MAX_AUDIO_DURATION_SEC=1800
WORKER_CONCURRENCY=1
WORKER_MAX_ATTEMPTS=3
ASR_PROVIDER=mock
LLM_PROVIDER=mock
ASR_MODEL=small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
```

Не использовать пример пароля в публичном или real-customer окружении. Если параметры изменяются, документировать их и добавлять конфигурационные тесты. `LLM_PROVIDER=mock` и `ASR_PROVIDER=mock` только для демо/CI.



---

# 01. Глобальный landscape: speech / conversation intelligence

**Срез:** 02.11.2026. **Метод:** desk research публичных продуктовых страниц, API-документации, help center, технических статей. **Ограничение:** не проведены покупательские интервью, hands-on тесты интерфейсов, проверки SLA и независимое сравнение точности; масштаб/выручка компаний не установлены. Строка «есть функция» означает **заявлено публично**, не верифицировано нами.

## 1. Таксономия (принципиально разные рынки)

- **Revenue / sales conversation intelligence**: Gong, Clari/Clari Copilot, Salesloft, Avoma, Jiminny. Фокус: сделки, риск, next steps, coaching, CRM; разговор — один источник вместе с email и CRM.
- **Contact-center quality management / CX analytics**: CallMiner, Observe.AI, Cresta, NICE CXone, Verint, Genesys, Uniphore, Convin, Dialpad, MiaRec, Aircall, CloudTalk. Фокус: потоки контактов, QA-критерии, compliance, coaching, customer experience.
- **CCaaS-native / hyperscaler**: Amazon Connect Customer conversational analytics (ранее Contact Lens), Google CX Insights/Quality AI, Azure Speech + Language. Преимущество: глубокое встраивание в инфраструктуру, зрелость облака; минус: привязка к экосистеме/доступности регионов и языков.
- **Call tracking / marketing attribution**: Invoca и платформы сквозной аналитики. Цель: связать причины звонка с рекламным источником и конверсией.
- **РФ, sales-focused**: SalesAI, imot.io, Rechka, а также Цифровой РОП/другие локальные продукты. Фокус: русская речь, Bitrix24/amoCRM/АТС, кастомные отчёты. Enterprise сегмент включает ЦРТ, Naumen и решения телеком-провайдеров; конкретные предложения подлежат отдельной проверке.

## 2. Матрица наблюдений (источники в конце документа)

| Сервис / регион | Позиционирование | Явно заявленные возможности | Что можно перенять | Неизвестно |
|---|---|---|---|---|
| Gong / США, global | Revenue intelligence | capture, transcript, objections, deal signals, CRM, coaching | аналитика **на уровне сделки**, не только звонка | внутренняя ML архитектура, индивидуальные метрики качества |
| Avoma / США, global | Sales calls/meetings | custom scorecards, timestamped evidence, human review | **evidence-backed scoring**, разная scorecard на тип звонка | реальные показатели точности |
| Salesloft / global | Revenue workflow | recording, AI insights, coaching, integrations, analytics | действие/коучинг после отчёта | техническая реализация |
| CallMiner / США, global | Enterprise CX | QA на всех взаимодействиях, темы, compliance, dashboards, root cause | аналитика частоты причин, аудиты | latency и цена конкретного внедрения |
| Observe.AI / США | Contact center QA | 100% coverage, extraction, QA, journey | customer journey и контроль качества | внутренние модели |
| Cresta / США | Contact center AI | conversation intelligence, coaching, quality, outcome linkage | workflow «найти проблему → исправить» | backend и точные benchmark |
| NICE CXone / global | CCaaS + WEM | QM формы, апелляции, coaching, аналитика | **human appeals + calibration** | детали хранения отдельных контуров |
| Dialpad / США | UCaaS/CCaaS | AI/manual/suggested scorecards, аналитика по агентам | human override + modes of review | сопоставимость с русским рынком |
| Uniphore / global | Enterprise interaction AI | multi-tenant conversation insights, topics, QA | платформенные общие сервисы для tenant identity | архитектура моделей |
| Convin / Индия, global | Contact center QA | transcription, automated QA, role reports, CRM | операционные отчёты QA | независимо подтверждённые claims |
| Amazon Connect / global | Cloud contact analytics | redaction PII, contact categorization, quality forms, external voice | data redaction, historical + live analytics | условия для РФ deployments |
| Google CX Insights / global | Cloud CX analytics | import, topics, sentiment, replay synced transcript, Quality AI | issue discovery и synchronized UI | применимость поставщика к РФ |
| Azure Speech+Language / global | AI primitives | post-call insights, PII, sentiment, summaries | использовать специализированные API как компоненты | русская телефония под ваш dataset |
| Genesys Cloud CX / global | CCaaS speech/text analytics | post-call transcripts, topics, sentiment, playback, dashboards; topic programs | встраивание аналитики в телефонию, reprocessing по новой taxonomy | РФ доступность/языковое качество |
| Zoom Revenue Accelerator / global | Revenue intelligence для встреч и телефонии | call summaries, deal pipeline/CRM syncing, scorecards, coaching, MCP access | **conversation → deal → CRM**, вспомогательные developer surfaces | архитектура моделей и независимая точность |
| Jiminny / Великобритания, global | Sales conversation intelligence | call insights, multi-call deal context, CRM writeback, coaching | анализ не только отдельного звонка, но группы встреч по сделке | внутренняя ML архитектура |
| Invoca / США | Marketing calls | call-to-campaign attribution, signals, summaries, CRM activation | связывание звонка с источником лида | полнота QA функционала |
| MiaRec / США, global | Запись + analytics + QA | опубликован operator pipeline, очереди, AI tasks, Auto QA, tenant-level queues/jobs | **реальный job/queue pipeline**, управляемые per-tenant лимиты и фильтры | внутренние модели и полнота деплоя |
| Aircall / global | Cloud telephony + AI Assist | automated scorecards по событиям завершения/тегирования, фильтры агент/номер/направление/длительность, приоритет правил | **event-driven scorecard routing** и выбор оцениваемого агента при переводе | независимая точность, условия РФ |
| CloudTalk / global | Cloud telephony + CI tiers | Basic: transcript, summary, topics, sentiment, score; Plus: custom topics/templates and auto-assignment | ступенчатые продуктовые планы, продвинутые настройки за отдельную плату | независимая точность, применимость в РФ |
| Verint / global | Enterprise quality intelligence | автоматизация QA, существующие каналы, governance и human workflow | AI-надстройка без замены контакт-центра, контроль внедрения | архитектура inference/DB |
| SalesAI / Россия | Sales intelligence | presigned S3 uploads, jobs, SSE, Pipeline API/Platform API, CRM fields, on-prem (заявлено) | реальный **API workflow** и tenant-level quotas | код, схема БД, SLA результатов |
| imot.io / Россия | Vertical speech analytics | отраслевые интеграции, CRM autofill, ЖК/лиды/стадии, BI export | контекст сделки и вертикальные workflow | фактические benchmark качества |
| Rechka / Россия | AI call review | custom report columns, фильтры до анализа, CRM, claims data РФ | предфильтрация «нецелевых» звонков для экономии | заявленные «98,7%» без независимого протокола |

**Нужно различать** функции «speech transcription», «conversation analytics», «autonomous coaching», «real-time agent assist». Их нельзя оценивать как идентичный продукт. Публичные claims «100% calls analyzed» означают coverage целевого потока, а не 100% точность.

## 3. Подтверждённые архитектурные наблюдения

### SalesAI (публичный API, не исходники)

- `POST /api/v1/calls/with-media` → presigned URL → PUT в объектное хранилище → complete → job → SSE progress → analyses.
- Отдельно документированы Pipeline API и Platform API (пользователи/tenants/квоты/OAuth).
- Обозначены настраиваемые scorecards, glossaries, webhooks, агрегированная аналитика; заявлены российское размещение и On-Premise.
- **Нельзя утверждать:** они используют Celery, Kafka, PostgreSQL, конкретную модель или C4-разбиение — это неизвестно.

### imot.io

- В публичном vertical-кейсе недвижимости — связка АТС, CRM, статусов сделки, объекта/ЖК и автоматического обогащения карточки.
- Продуктова́я вертикаль помогает перейти от generic «тема звонка» к полезному полю «бронь/показ/бюджет/договор».
- **Вывод:** модель данных должна допускать `crm_context` и версионированную отраслевую таксономию, но интеграцию начать с одного клиента.

### MiaRec — реальный технический pipeline из operator guide

Публичная инструкция оператора **прямо описывает** шаги (это не вывод из маркетинга): ingest записи / запись звонка вызывает событие → job транскрибирует аудио → следующее задание выполняет AI-анализ → результаты пишутся в данные диалога. Между этапами — очереди, есть job filters, ограничения и настройки выполнения по tenants и мониторинг заданий. Конкретные имена брокера, СУБД и развёрнутые модели из этого документа не следуют.

**Архитектурный урок:** мы воспроизводим принцип orchestration **через долговечные задания, состояния и очереди**, но не обязаны сразу выделять отдельный microservice на этап. Обязательны per-tenant concurrency/quotas, retry, DLQ и audit trail. См. https://docs.miarec.com/operator-guide/conversation-analytics/pipeline-overview/.

### Aircall — документированный выбор scorecard по событию и правилам

Документация Aircall перечисляет фильтры автоматически оцениваемых звонков: агенты/команды, линии, inbound/outbound, длительность и теги; триггеры — завершение разговора или обновление тегов, выбирается первое совпавшее правило по приоритету, возможна оценка первого/последнего агента после перевода. В Aircall при повторном прогоне результат может заменяться — **мы сознательно выбираем другой вариант**: immutable `analysis_runs` + `latest_approved_run_id` для расследования спорных оценок и сравнения версий.

Для P1: добавлять conditional rules и маршрутизацию в разные scorecards. Для P0: **одна явная scorecard** на tenant/workspace без конструктора правил. Источник https://support.aircall.io/en-gb/articles/28736864368669.

### Genesys, Zoom Revenue Accelerator и Jiminny — граница «звонок» vs «сделка»

Genesys Cloud публикует post-call схему аналитики, topic spotting, sentiment, просмотр аудио и синхронного транскрипта, а также возможность более низколатентной подписки на транскрипты по Notifications API. Для нашего batch-first пилота realtime не обязателен. Zoom Revenue Accelerator публично описывает CRM-sync, scorecards и deal-level intelligence; Zoom также выпустил MCP-коннектор с доступом к расшифровкам, сделкам и оценкам для инструментов, включая Codex. Jiminny предоставляет insights как по одному звонку, так и в контексте нескольких разговоров по сделке.

**Решение:** entity `call` остаётся P0; `crm_deal_id` — optional link, а полноценная аналитика по сделке/истории контактов — P2. Возможный MCP/read API не должен предоставлять прямой доступ к исходным записям без RBAC и tenant scoping. Источники: https://help.genesys.cloud/articles/speech-and-text-analytics-overview/ · https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0059301 · https://godevelopers.zoom.us/docs/mcp/zoom-revenue-accelerator-mcp-server/ · https://jiminny.com/product/conversation-intelligence.

### CloudTalk и Verint — продуктовая упаковка и enterprise workflow

CloudTalk явно делит Conversation Intelligence на Basic (транскрипт, summary, темы, sentiment, call scoring) и Plus (настраиваемые темы и шаблоны, автоматическое назначение): это подтверждает возможность строить в дальнейшем **планы по степени настройки**, а не только по числу минут. Никакие опубликованные цены международного продукта нельзя механически перенести на российский рынок. Verint описывает quality management как AI-надстройку над существующими системами контактов и управления рабочими процессами; не нужно заменять АТС клиента. Источники: https://help.cloudtalk.io/en/articles/10191313-conversation-intelligence-plans-ci-basic-and-ci-plus · https://www.verint.com/guides/automated-quality-management/.

### Avoma, Dialpad и NICE

- Avoma явно акцентирует **timestamped evidence** для каждой оценки и человеческую проверку пограничных случаев.
- Dialpad документирует три режима: AI-scored, AI-suggested, manual.
- NICE описывает апелляции сотрудников, оценщиков и калибровку их решений.
- **Вывод:** оценка не должна быть только числом. Нужны `not_applicable`, доказательства, исправление/отмена человеком и версия.

### Amazon и Google

- Amazon Connect выделяет PII redaction, правила категоризации, quality evaluation, playback.
- Google CX Insights — pipeline ingest → topic modeling → human curation → deploy taxonomy, а также replay с синхронными аннотациями.
- **Вывод:** темы обращений — изменяемая таксономия; UX должен связывать показатели с исходными разговорами.

## 4. Повторяющиеся паттерны зрелого продукта

1. Встраивание в существующие источники (записи, CRM), а не замена телефонии.
2. Не только summary, но **настраиваемая scorecard и evidence**.
3. Drill-down: агрегат → команда → сотрудник → звонок → таймкод.
4. Контроль качества модели с ручным override, апелляциями, sampling.
5. Связь с бизнес-исходом: отказ, назначение встречи, next action, CRM outcome.
6. Privacy, retentions, RBAC и альтернативные режимы размещения.
7. Инкрементальные интеграции: ingestion и обратная запись результатов по контрактам.
8. Условная глубина анализа: дешёвые filters/classification + тяжёлые проверки для релевантных звонков.

## 5. Возможности дифференциации (гипотезы, не установленное преимущество)

- **A. Проверяемые QA-оценки с апелляцией:** доказательство до секунды, объяснение, ручной override, согласованность контролёров.
- **B. Быстрый пилот в одной vertical:** например, 1 вид продаж и 1 основная CRM/АТС; 48-часовая настройка после получения доступа — **не обещание**, пока не измерена.
- **C. Прозрачная экономическая модель:** стоимость/мин, error budget, latency, обработанные минуты и % отсутствующих доказательств.
- **D. Privacy-first deployment:** документированный контур РФ, возможность self-host провайдеров, DPA, логическое разделение tenants.
- **E. Гибкая taxonomy:** настройки через конфигурацию, versioned scorecards, A/B модельных pipeline без перезаписи истории.

## 6. Что НЕ стоит копировать до первого пилота

Live coaching, chat/email omnichannel, deal forecasting, полноценный BI-конструктор, emotion по акустике, full RAG, обучение собственной LLM, автопринятие кадровых решений, SSO enterprise, все CRM одновременно.

## 7. Методология следующего рыночного этапа (короткая)

Сделать 5–8 интервью с руководителями контроля качества / продаж; попросить 10–20 обезличенных или разрешённых записей и их реальные чек-листы. Демонстрировать **аналитический результат и проигрывание evidence**, а не «AI». Замерять: насколько много ручной проверки снято, сколько ошибок нашли, сколько времени ушло на внедрение, сколько стоит обработка.

## 8. Источники

- Genesys: https://help.genesys.cloud/articles/speech-and-text-analytics-overview/
- Zoom Revenue Accelerator: https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0059301
- Zoom MCP: https://godevelopers.zoom.us/docs/mcp/zoom-revenue-accelerator-mcp-server/
- Jiminny: https://jiminny.com/product/conversation-intelligence
- MiaRec pipeline: https://docs.miarec.com/operator-guide/conversation-analytics/pipeline-overview/
- Aircall scoring: https://support.aircall.io/en-gb/articles/28736864368669
- CloudTalk tiers: https://help.cloudtalk.io/en/articles/10191313-conversation-intelligence-plans-ci-basic-and-ci-plus
- Verint: https://www.verint.com/guides/automated-quality-management/
- Gong: https://www.gong.io/conversation-intelligence
- Avoma: https://www.avoma.com/revenue-execution/score-calls-against-a-rubric
- Salesloft: https://help.salesloft.com/s/topic/0TOVq000000eXJpOAM/conversation-intelligence
- CallMiner: https://callminer.com/conversation-analytics/conversation-analytics
- Observe.AI: https://www.observe.ai/platform/interaction-intelligence
- Cresta: https://cresta.com/guides/conversational-analytics
- NICE: https://resources.nice.com/wp-content/uploads/2024/09/CXone-Quality-Management-Brochure.pdf
- Dialpad: https://help.dialpad.com/docs/ai-scorecards
- Uniphore: https://help.uniphore.com/page/en/welcome-to-conversation-insights-agent.html
- Convin: https://www.convin.ai/en-us/products/automated-quality-management
- Amazon: https://docs.aws.amazon.com/connect/latest/adminguide/contact-lens.html
- Google CX Insights: https://docs.cloud.google.com/gemini-enterprise-cx/insights
- Azure: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/call-center-overview
- Invoca: https://www.invoca.com/platform/signal-ai
- SalesAI API: https://salesai.ru/docs/api-pipeline/ · Security: https://salesai.ru/docs/security-compliance/
- imot.io: https://imot.io/developers · Product: https://imot.io/
- Rechka: https://rechka.ai/produkt/analiz-zvonkov-ii/
- Дополнительный **заинтересованный** обзор рынка РФ (проверять первичными источниками): https://rechka.ai/blog/sravnenie-rechevoy-analitiki/

Обновлять матрицу не реже одного раза в квартал; для pricing/availability — перед коммерческим предложением.



---

# 15. Research bibliography and evidence ledger

**Research date:** 2026-11-02. Vendor pages are vendor claims, not independent performance audits. Documentation version/availability may change. Legal references require current-text check and professional sign-off. Sources selected to support architecture, industry patterns, ML and operations; this is a *global representative landscape*, not an exhaustive census of every provider.

## Competition / global vendors — primary product documents

| ID | What source establishes | URL |
|---|---|---|
| C01 | Gong conversation intelligence, coaching, deal signals and CRM | https://www.gong.io/conversation-intelligence |
| C02 | Avoma rubric-based scoring + timestamp evidence + human review | https://www.avoma.com/revenue-execution/score-calls-against-a-rubric |
| C03 | Salesloft call insights and coaching | https://help.salesloft.com/s/topic/0TOVq000000eXJpOAM/conversation-intelligence |
| C04 | CallMiner analysis, scoring, compliance, CX dashboards | https://callminer.com/conversation-analytics/conversation-analytics |
| C05 | Observe.AI interaction intelligence, full coverage QA | https://www.observe.ai/platform/interaction-intelligence |
| C06 | Cresta connected conversation insights and coaching | https://cresta.com/guides/conversational-analytics |
| C07 | NICE QM with appeals/calibration | https://resources.nice.com/wp-content/uploads/2024/09/CXone-Quality-Management-Brochure.pdf |
| C08 | Dialpad AI/manual/assisted scorecards | https://help.dialpad.com/docs/ai-scorecards |
| C09 | Uniphore multi-tenant conversation insights | https://help.uniphore.com/page/en/welcome-to-conversation-insights-agent.html |
| C10 | Convin automated QA | https://www.convin.ai/en-us/products/automated-quality-management |
| C11 | Amazon Connect conversational analytics, redaction, quality | https://docs.aws.amazon.com/connect/latest/adminguide/contact-lens.html |
| C12 | Google CX Insights capabilities | https://docs.cloud.google.com/gemini-enterprise-cx/insights |
| C13 | Google topic model workflow | https://docs.cloud.google.com/gemini-enterprise-cx/insights/topic-modeling-overview |
| C14 | Azure call center workflow | https://learn.microsoft.com/en-us/azure/ai-services/speech-service/call-center-overview |
| C15 | Invoca Signal AI and marketing attribution | https://www.invoca.com/platform/signal-ai |
| C16 | SalesAI API: presigned S3, jobs, SSE, Platform vs Pipeline | https://salesai.ru/docs/api-pipeline/ |
| C17 | SalesAI compliance/on-prem claims | https://salesai.ru/docs/security-compliance/ |
| C18 | SalesAI official description of model and RAG/fine-tuning | https://salesai.ru/docs/docs-overview/ |
| C19 | imot.io property development CRM/ATC flow | https://imot.io/developers |
| C20 | imot.io features | https://imot.io/ |
| C21 | Rechka filters and configurable analysis | https://rechka.ai/produkt/analiz-zvonkov-ii/ |
| C23 | MiaRec operator guide: explicitly documented event/queue/transcription/AI jobs pipeline, tenant limitations | https://docs.miarec.com/operator-guide/conversation-analytics/pipeline-overview/ |
| C24 | Aircall automated scoring triggers, rule priority, agents, tags; existing result replaced | https://support.aircall.io/en-gb/articles/28736864368669 |
| C25 | CloudTalk CI Basic/Plus segmentation and automatic scorecard assignment | https://help.cloudtalk.io/en/articles/10191313-conversation-intelligence-plans-ci-basic-and-ci-plus |
| C26 | Verint quality management ecosystem and AI capabilities | https://www.verint.com/guides/automated-quality-management/ |
| C27 | Genesys Cloud: speech/text analytics, post-call topics and sentiment, Notifications API | https://help.genesys.cloud/articles/speech-and-text-analytics-overview/ |
| C28 | Zoom Revenue Accelerator product/CRM context and scorecards | https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0059301 |
| C29 | Zoom Revenue Accelerator MCP tool surface — documented optional AI-agent interface | https://godevelopers.zoom.us/docs/mcp/zoom-revenue-accelerator-mcp-server/ |
| C30 | Jiminny multi-call/deal insights and CRM integrations | https://jiminny.com/product/conversation-intelligence |
| C22 | Rechka competitor comparison: **interested party, treat as market map only** | https://rechka.ai/blog/sravnenie-rechevoy-analitiki/ |

## Models / operational technology

| ID | Source | URL |
|---|---|---|
| M01 | Whisper model card, limitations, languages, checkpoints | https://github.com/openai/whisper/blob/main/model-card.md |
| M02 | faster-whisper implementation, quantization and benchmark notes | https://github.com/SYSTRAN/faster-whisper |
| M03 | pyannote Community-1 model card, 16k mono, offline support | https://huggingface.co/pyannote/speaker-diarization-community-1 |
| M04 | NVIDIA NeMo diarization architectures | https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/speaker_diarization/models.html |
| M05 | Qwen3 model family and licensing | https://github.com/QwenLM/Qwen3 |
| M06 | vLLM current structured output API | https://docs.vllm.ai/en/latest/features/structured_outputs/ |
| M07 | SaluteSpeech 8k callcenter acoustic model | https://developers.sber.ru/docs/ru/salutespeech/guides/recognition/improvement |
| M08 | SaluteSpeech corporate tariff (31 Aug 2026) | https://developers.sber.ru/docs/ru/salutespeech/tariffs/legal-tariffs |
| M09 | SaluteSpeech new-customer restriction (15 Jul 2026) | https://developers.sber.ru/docs/ru/salutespeech/quick-start/integration-entities |
| M10 | MLflow Registry: lineage, versions, aliases | https://www.mlflow.org/docs/latest/model-registry/ |

## Peer-reviewed / research / engineering

| ID | Citation and relevance | URL |
|---|---|---|
| R01 | D. Sculley et al., *Hidden Technical Debt in Machine Learning Systems*, NeurIPS 2015 — pipeline complexity and hidden coupling | https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html |
| R02 | E. Breck et al., *What's Your ML Test Score?*, NIPS 2016 workshop — test readiness | https://research.google/pubs/whats-your-ml-test-score-a-rubric-for-ml-production-systems/ |
| R03 | Martin Zinkevich, *Rules of Machine Learning* — infrastructure and simple models first | https://developers.google.com/machine-learning/guides/rules-of-ml/ |
| R04 | Google ML Productionization — monitoring, rollback, deployment | https://developers.google.com/machine-learning/managing-ml-projects/production |
| R05 | Bavaresco et al., *LLMs instead of Human Judges?*, 2024 — disagreement/bias, human labels required | https://arxiv.org/abs/2406.18403 |
| R06 | Zheng et al., *Judging LLM-as-a-Judge with MT-Bench*, 2023 — evaluator biases | https://arxiv.org/abs/2306.05685 |
| R07 | Google SRE book, monitoring distributed systems — alert and SLI principles | https://sre.google/sre-book/monitoring-distributed-systems/ |
| R08 | Google SRE service practices — error budgets and SLO | https://sre.google/sre-book/service-best-practices/ |
| R09 | Chris Richardson microservice patterns — outbox, idempotency, boundaries | https://microservices.io/patterns/ |
| R10 | Celery Tasks — acknowledgement, retries, idempotency | https://docs.celeryq.dev/en/stable/userguide/tasks.html |
| R11 | OpenTelemetry semantic conventions — traces/metrics/logs | https://opentelemetry.io/docs/concepts/semantic-conventions/ |
| R12 | NIST AI RMF 1.0 and Playbook, continuous AI risks | https://airc.nist.gov/airmf-resources/playbook/ |
| R13 | OWASP API Top 10 2023, auth/SSRF/resource risks | https://api-security.owasp.org/editions/2023/en/0x11-t10/ |

## РФ regulation / integration

| ID | Reference | URL |
|---|---|---|
| L01 | 152-ФЗ art 6(3) on processor instructions | https://www.consultant.ru/document/cons_doc_LAW_61801/315f051396c88f1e4f827ba3f2ae313d999a1873/ |
| L02 | 152-ФЗ art 18(5), storage/localization restrictions | https://www.consultant.ru/document/Cons_doc_LAW_61801/cbf4e15b7c330f9372e876cdf2bc928bad7950ef/ |
| L03 | Минцифры 2025 explanatory letter | https://www.consultant.ru/document/cons_doc_LAW_511584/ |
| I01 | amoCRM webhooks API | https://www.amocrm.ru/developers/content/crm_platform/webhooks-api |
| I02 | Bitrix24 external telephony integration | https://apidocs.bitrix24.ru/tutorials/telephony/index |

## Evidence policy

- `documented`: explicit vendor primary source, but not independently validated.
- `research`: paper or open documentation supports general best practice, not vendor implementation.
- `design-proposal`: architecture trade-off recommended here, not external factual claim.
- `hypothesis`: numbers, performance, market wedge/ROI, business targets pending benchmark or interview.

## Important unknowns / research gaps

- Proprietary internal stacks, model parameters, deployment recipes, real latency and unit costs of Gong/CallMiner/SalesAI/imot.io: **not public**.
- Actual Russian call ASR/LLM benchmarking and chosen provider commercial approval: **not tested**.
- Security compliance of this future product, certifications, DPA and corporate hosting: **not established**.
- TAM/SAM/SOM and company revenue/market share: no reliable audited data gathered, do **not** invent numbers.
- Specific pricing and regional availability as of deployment: re-check directly with providers.
