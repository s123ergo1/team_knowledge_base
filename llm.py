"""
LLM client via ProxyAPI (OpenAI-compatible).
ProxyAPI base URL: https://api.proxyapi.ru/openai/v1
"""
import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url="https://api.proxyapi.ru/openai/v1",
)

MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

SYSTEM_PROMPT = """Ты — корпоративный ИИ-ассистент базы знаний компании.
Твоя задача — отвечать на вопросы сотрудников строго на основе предоставленного контекста из документов.

Правила:
1. Отвечай ТОЛЬКО на основе контекста. Не придумывай и не дополняй информацию.
2. Если контекст пустой или нерелевантен — honest сообщи об этом и установи needs_review=true.
3. Если вопрос НЕ относится к рабочим, корпоративным или деловым темам (личные вопросы, развлечения, стихи, бытовые вещи, техника вне работы и т.п.) — установи out_of_scope=true.
4. Всегда отвечай на русском языке.
5. Будь лаконичен и конкретен.

Ты ОБЯЗАН вернуть ответ строго в формате JSON (без markdown-обёртки):
{
  "answer": "текст ответа сотруднику",
  "confidence_score": 0.95,
  "needs_review": false,
  "review_reason": null,
  "out_of_scope": false
}

Поля:
- answer: понятный ответ для сотрудника
- confidence_score: число от 0.0 до 1.0 (уверенность в ответе)
- needs_review: true если нет данных в контексте или уверенность < 0.7
- review_reason: строка с причиной если needs_review=true, иначе null
- out_of_scope: true если вопрос не относится к корпоративным/рабочим темам (в этом случае needs_review должен быть false)
"""


def call_llm(question: str, context: str) -> dict:
    """
    Вызывает LLM через ProxyAPI. Возвращает распарсенный dict с полями:
    answer, confidence_score, needs_review, review_reason, sources_found.
    При любой ошибке возвращает словарь с needs_review=True.
    """
    user_message = f"""Контекст из базы знаний:
{context if context else "(контекст не найден)"}

Вопрос сотрудника: {question}"""

    logger.info("LLM call: model=%s question_len=%d context_len=%d",
                MODEL, len(question), len(context))

    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content.strip()
    logger.debug("LLM raw response: %s", raw)

    # Убираем возможную markdown-обёртку ```json ... ```
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = json.loads(raw)

    # Гарантируем наличие всех полей
    result.setdefault("answer", "Ответ не получен.")
    result.setdefault("confidence_score", 0.0)
    result.setdefault("needs_review", True)
    result.setdefault("review_reason", None)
    result.setdefault("out_of_scope", False)

    # out_of_scope не требует ревью эксперта
    if result["out_of_scope"]:
        result["needs_review"] = False
        result["review_reason"] = None

    # Если уверенность низкая — отправляем на ревью
    elif result["confidence_score"] < 0.7 and not result["needs_review"]:
        result["needs_review"] = True
        result["review_reason"] = f"Низкая уверенность модели: {result['confidence_score']:.2f}"

    return result
