# Team Knowledge Base

Корпоративная база знаний с ИИ-ассистентом. Сотрудники задают вопросы — система ищет ответ в загруженных документах через LLM. Нерелевантные вопросы автоматически отклоняются; вопросы без уверенного ответа передаются эксперту на ручную проверку.

---

## Архитектура системы

```
USER LAYER                    WEB PANELS                    BACKEND API (FastAPI)
┌──────────────┐             ┌──────────────────┐          ┌────────────────────────
│ Пользователь │──HTTP──────▶│ Web-панель (/user)│──GET/POST▶│ POST /api/queries      │
│ (сотрудник)  │             │ • Топ-10 FAQ     │          │ GET /api/queries       │
└──────────────┘             │ • Задать вопрос  │          │ POST /queries/{id}/    │
                             └──────────────────┘          │   process              │
┌──────────────┐             ┌──────────────────┐          │ POST /api/documents/   │
│ Администратор│──HTTP──────▶│ Админ-панель (/) │──all────▶│   upload               │
│              │             │ • Витрина        │ endpoints│ GET /api/faq/top10     │
└──────────────┘             │ • Детали         │          └───────────┬────────────┘
                             │ • Ручная проверка│                      │
                             │ • Загрузка файлов│                      │
                             └──────────────────┘                      │
                                                                       ▼
                                                          ┌────────────────────────┐
                                                          │   SQLite БД            │
                                                          │ • documents            │
                                                          │ • queries              │
                                                          │ • reviews              │
                                                          │ • resolved_memory      │
                                                          │ • audit_runs           │
                                                          └───────────┬────────────┘
                                                                      │
                                                          ┌───────────▼────────────┐
                                                          │  File Processor        │
                                                          │  (PyPDF2, python-docx) │
                                                          │  PDF/DOCX/TXT → text   │
                                                          └───────────┬────────────┘
                                                                      │
                                                          ┌───────────▼────────────┐
                                                          │  ИИ-Оркестратор (LLM)  │
                                                          │  строгий JSON +        │
                                                          │  температура 0.3       │
                                                          └───────────┬────────────┘
                                                                      │ JSON ответ
                                                          ┌───────────▼────────────┐
                                                          │  Контроль качества     │
                                                          │  ✓ confidence ≥ 0.7?   │
                                                          │  ✓ JSON валиден?       │
                                                          │  ✓ Контекст найден?    │
                                                          └─────┬─────────────┬────┘
                                                                │             │
                                                    ✅ Уверен   │             │ ❌ needs_review=true
                                                                ▼             ▼
                                                          ┌──────────┐  ┌──────────────┐
                                                          │ Статус:  │  │ Ручная       │
                                                          │processed │  │ проверка     │
                                                          └──────────┘  │ (эксперт)    │
                                                                        └──────┬───────┘
                                                                               │
                                                                               ▼
                                                                      ┌──────────────┐
                                                                      │  reviews     │
                                                                      │  в БД        │
                                                                      └──────────────┘

AUDIT LAYER — audit_runs (от всех компонентов)
action │ input │ output │ status │ duration_ms │ created_at
```

### Сценарий 1 — Сотрудник задаёт вопрос

1. Пользователь открывает `/user` → видит Топ-10 FAQ.
2. Кликает на вопрос или вводит свой → Web-панель отправляет `POST /api/queries`.
3. Backend API создаёт запись в `queries` (статус: `new`).
4. Сразу вызывает `POST /api/queries/{id}/process`.
5. ИИ-Оркестратор ищет контекст в `documents`, генерирует строгий JSON.
6. Контроль качества проверяет результат:
   - `confidence_score ≥ 0.7` и контекст найден → статус `processed` ✅
   - Иначе → статус `needs_review` ❌ → уходит в Ручную проверку.
7. Все шаги пишутся в `audit_runs`.

### Сценарий 2 — Админ загружает документ

1. Администратор открывает `/` → секция «Загрузка файлов».
2. Выбирает PDF / DOCX / TXT → Web-панель отправляет `POST /api/documents/upload`.
3. File Processor извлекает текст из файла.
4. Backend API сохраняет в `documents` (`title`, `content`, `category`).
5. Теперь ИИ может искать ответы в этом документе.

### Сценарий 3 — Ручная проверка

1. Администратор видит оранжевый бейджик «Требует проверки» в витрине.
2. Кликает на заявку → видит Детали + сырой JSON из аудита.
3. Читает причину: `review_reason: "В базе знаний не найдено релевантных документов"`.
4. Может загрузить нужный документ через «Загрузку файлов».
5. Система запомнит ответ в `resolved_memory` для будущих похожих вопросов.

---

## Структура проекта

```
team_knowledge_base/
├── main.py              # FastAPI — все эндпоинты
├── database.py          # SQLAlchemy модели и подключение к БД
├── llm.py               # Клиент ProxyAPI / OpenAI
├── file_processor.py    # Извлечение текста из PDF, DOCX, TXT
├── static/
│   ├── index.html       # Админ-панель (дашборд, ручная проверка, детали)
│   └── user.html        # Панель сотрудника (FAQ + вопрос к ИИ)
├── team_knowledge.db    # SQLite база данных (создаётся автоматически)
├── .env                 # Переменные окружения (не коммитить!)
├── .env.example         # Шаблон переменных окружения
├── Dockerfile           # Образ для контейнеризации
└── docker-compose.yml   # Запуск через Docker Compose
```

---

## Переменные окружения

Скопируйте шаблон и заполните значения:

```bash
cp .env.example .env
```

| Переменная | Описание | Пример |
|---|---|---|
| `DATABASE_URL` | Путь к SQLite БД | `sqlite:///./team_knowledge.db` |
| `LLM_API_KEY` | API-ключ ProxyAPI / OpenAI | `sk-...` |
| `LLM_MODEL` | Модель LLM | `gpt-4o-mini` |
| `LLM_TEMPERATURE` | Температура генерации (0.0–1.0) | `0.3` |

---

## Установка и запуск

### Вариант 1 — локально (venv)

```bash
# 1. Создать виртуальное окружение
python -m venv venv

# 2. Активировать
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Создать .env (см. раздел выше)

# 5. Запустить сервер
python -m uvicorn main:app --reload --port 8001
```

### Вариант 2 — Docker

```bash
# Собрать образ и запустить контейнер
docker compose up -d

# Остановить
docker compose down

# Логи в реальном времени
docker compose logs -f
```

После запуска:
- Панель сотрудника: http://localhost:8001/user
- Админ-панель: http://localhost:8001/
- Swagger UI: http://localhost:8001/docs

---

## Примеры запросов (curl)

### 1. Добавить документ в базу знаний

```bash
curl -X POST http://localhost:8001/api/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Политика отпусков",
    "content": "Сотрудник имеет право на 28 календарных дней отпуска в год. Заявление подаётся за 2 недели до начала отпуска через HR-портал.",
    "category": "HR"
  }'
```

### 2. Создать вопрос сотрудника

```bash
curl -X POST http://localhost:8001/api/queries \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "Иванов Иван",
    "question": "Как оформить отпуск и за сколько дней подать заявление?"
  }'
```

### 3. Запустить ИИ-обработку запроса (подставьте нужный query_id)

```bash
curl -X POST http://localhost:8001/api/queries/1/process
```

### 4. Получить детали запроса с ответом ИИ и ответом эксперта

```bash
curl http://localhost:8001/api/queries/1
```

### 5. Загрузить файл (PDF / DOCX / TXT)

```bash
curl -X POST http://localhost:8001/api/documents/upload \
  -F "file=@регламент.pdf" \
  -F "category=Юридический"
```

### 6. Топ-10 FAQ

```bash
curl http://localhost:8001/api/faq/top10
```

---

## База данных

SQLite-файл: `team_knowledge.db` — создаётся автоматически при первом запуске рядом с `main.py`.

### Просмотр данных

Через Python:

```bash
python -c "
from database import SessionLocal, Query, AuditRun
db = SessionLocal()
print('=== Запросы ===')
for q in db.query(Query).all():
    print(f'  [{q.id}] {q.user_name}: {q.question[:60]} — {q.status}')
print('=== Аудит ===')
for a in db.query(AuditRun).order_by(AuditRun.id.desc()).limit(5).all():
    print(f'  [{a.id}] {a.action} | {a.status} | {a.duration_ms}ms')
db.close()
"
```

Через SQLite CLI:

```bash
sqlite3 team_knowledge.db ".tables"
sqlite3 team_knowledge.db "SELECT id, user_name, status FROM queries ORDER BY id DESC LIMIT 10;"
sqlite3 team_knowledge.db "SELECT id, action, status, duration_ms FROM audit_runs ORDER BY id DESC LIMIT 5;"
```

### Экспорт в CSV

В админ-панели нажмите кнопку **«Экспорт CSV»** — выгрузятся все запросы включая отклонённые и переданные эксперту.

---

## Воспроизведение сценария «ручная проверка»

Ручная проверка срабатывает, когда ИИ не нашёл релевантных документов или уверенность ниже порога.

### Пошаговый сценарий:

```bash
# Шаг 1. Создать запрос по теме, которой НЕТ в базе знаний
curl -X POST http://localhost:8001/api/queries \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Тестовый Сотрудник", "question": "Какой порядок согласования командировки в другой город?"}'

# Шаг 2. Запустить обработку (id из ответа шага 1, например 1)
curl -X POST http://localhost:8001/api/queries/1/process

# Ответ: "new_status": "needs_review" — запрос ушёл эксперту

# Шаг 3. Эксперт отправляет ответ
curl -X POST http://localhost:8001/api/queries/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_name": "Эксперт HR Петрова",
    "correct_answer": "Командировка согласуется через руководителя отдела и оформляется в 1С за 3 рабочих дня до отъезда.",
    "comment": "В базе знаний нет документа по командировкам, добавить регламент."
  }'

# Шаг 4. Проверить — статус стал "resolved", ответ эксперта сохранён
curl http://localhost:8001/api/queries/1
```

Ответ эксперта виден в:
- поле `expert_answer` JSON-ответа эндпоинта `/api/queries/{id}`
- зелёном блоке на экране деталей в **админ-панели**
- кнопке «Проверить — эксперт уже ответил?» в **панели сотрудника**

