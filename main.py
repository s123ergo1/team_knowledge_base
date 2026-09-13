import json
import logging
import re
import time
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from database import SessionLocal, Query, AuditRun, Document, Review, ResolvedMemory
from llm import call_llm
from file_processor import extract_text_from_file, SUPPORTED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Team Knowledge Base API")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/user", response_class=HTMLResponse)
def read_user_panel():
    """Отдает панель для обычного сотрудника."""
    with open("static/user.html", "r", encoding="utf-8") as f:
        return f.read()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)


@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    category: str = "Общее",
    db: Session = Depends(get_db),
):
    """Загружает файл (PDF/DOCX/TXT) и добавляет его содержимое в базу знаний."""
    if not any(file.filename.lower().endswith(ext) for ext in SUPPORTED):
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат. Разрешены: {', '.join(SUPPORTED)}",
        )

    file_content = await file.read()
    text_content = extract_text_from_file(file_content, file.filename)

    if text_content.startswith("["):
        raise HTTPException(status_code=422, detail=text_content)

    db_doc = Document(title=file.filename, content=text_content, category=category)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    logger.info("File uploaded: id=%d name=%s chars=%d", db_doc.id, file.filename, len(text_content))
    return {
        "message": "Файл успешно загружен",
        "id": db_doc.id,
        "filename": file.filename,
        "characters": len(text_content),
        "category": category,
    }


@app.post("/api/documents", status_code=201)
def add_document(doc: DocumentCreate, db: Session = Depends(get_db)):
    """Добавляет регламент в базу знаний."""
    db_doc = Document(title=doc.title, content=doc.content, category=doc.category)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    logger.info("Document added: id=%d title=%s", db_doc.id, doc.title)
    return {"message": "Document added", "id": db_doc.id}


class ReviewCreate(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=100)
    correct_answer: str = Field(min_length=3)
    comment: str = Field(default="", max_length=1000)


@app.post("/api/queries/{query_id}/review", status_code=201)
def submit_review(query_id: int, review: ReviewCreate, db: Session = Depends(get_db)):
    """Эксперт отправляет проверенный ответ на заявку."""
    query = db.query(Query).filter(Query.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    if query.status != "needs_review":
        raise HTTPException(status_code=400, detail=f"Query status is '{query.status}', expected 'needs_review'")

    db_review = Review(
        query_id=query_id,
        reviewer_name=review.reviewer_name,
        correct_answer=review.correct_answer,
        comment=review.comment,
        status="approved",
    )
    db.add(db_review)

    # Сохраняем финальный ответ в ResolvedMemory для будущего использования
    resolved = ResolvedMemory(
        query_id=query_id,
        final_answer=review.correct_answer,
    )
    db.add(resolved)

    query.status = "resolved"
    db.commit()

    logger.info("Review submitted: query_id=%d reviewer=%s", query_id, review.reviewer_name)
    return {
        "query_id": query_id,
        "new_status": query.status,
        "expert_answer": review.correct_answer,
        "reviewer": review.reviewer_name,
        "message": "Review submitted",
    }


class QueryCreate(BaseModel):
    user_name: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=3, max_length=2000)


@app.post("/api/queries", status_code=201)
def create_query(query: QueryCreate, db: Session = Depends(get_db)):
    db_query = Query(user_name=query.user_name, question=query.question, status="new")
    db.add(db_query)
    db.commit()
    db.refresh(db_query)
    logger.info("Query created: id=%d user=%s", db_query.id, query.user_name)
    return {"id": db_query.id, "status": db_query.status, "message": "Query created"}


@app.get("/api/queries/{query_id}")
def get_query_details(query_id: int, db: Session = Depends(get_db)):
    """Отдает полную информацию по одной заявке (для экрана Деталей)."""
    query = db.query(Query).filter(Query.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    audit = (
        db.query(AuditRun)
        .filter(AuditRun.input_data.contains(f'"query_id": {query_id}'))
        .order_by(AuditRun.id.desc())
        .first()
    )

    review = (
        db.query(Review)
        .filter(Review.query_id == query_id, Review.status == "approved")
        .order_by(Review.id.desc())
        .first()
    )

    logger.info("Query details fetched: id=%d", query_id)
    return {
        "id": query.id,
        "user": query.user_name,
        "question": query.question,
        "status": query.status,
        "created_at": query.created_at.isoformat(),
        "audit_output": audit.output_data if audit else None,
        "expert_answer": review.correct_answer if review else None,
        "expert_name": review.reviewer_name if review else None,
        "expert_comment": review.comment if review else None,
    }


@app.get("/api/faq/top10")
def get_top_faq(db: Session = Depends(get_db)):
    """Возвращает Топ-10 самых частых успешно обработанных вопросов."""
    faq_list = (
        db.query(Query.question, func.count(Query.id).label("count"))
        .filter(Query.status == "processed")
        .group_by(Query.question)
        .order_by(func.count(Query.id).desc())
        .limit(10)
        .all()
    )

    if not faq_list:
        return [
            {"question": "Как оформить отпуск?", "count": 15},
            {"question": "Какой лимит на суточные?", "count": 12},
            {"question": "Как запросить доступ к БД?", "count": 8},
        ]

    logger.info("FAQ top10 fetched: %d items", len(faq_list))
    return [{"question": q.question, "count": q.count} for q in faq_list]


@app.get("/api/queries")
def get_queries(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    queries = db.query(Query).offset(skip).limit(limit).all()
    logger.info("Queries fetched: skip=%d limit=%d count=%d", skip, limit, len(queries))
    return [
        {
            "id": q.id,
            "user": q.user_name,
            "question": q.question,
            "status": q.status,
            "created_at": q.created_at.isoformat(),
        }
        for q in queries
    ]


@app.post("/api/queries/{query_id}/process")
def process_query(query_id: int, db: Session = Depends(get_db)):
    """
    ИИ-обработка с контролем качества и аудитом.
    Имитирует работу LLM: ищет контекст, формирует строгий JSON,
    оценивает уверенность и решает, нужна ли ручная проверка.
    """
    query = db.query(Query).filter(Query.id == query_id).first()
    if not query:
        logger.warning("Process failed: query id=%d not found", query_id)
        raise HTTPException(status_code=404, detail="Query not found")

    start_time = time.time()
    action = "llm_process_with_qc"
    status = "success"
    error_msg = None
    llm_output = {}

    try:
        # RAG: поиск релевантных документов по ключевым словам
        words = re.findall(r'\w{4,}', query.question.lower())
        filters = []
        for word in words:
            filters.append(Document.content.ilike(f"%{word}%"))
            filters.append(Document.title.ilike(f"%{word}%"))

        found_docs = db.query(Document).filter(or_(*filters)).limit(3).all() if filters else []
        context_text = "\n\n".join(
            f"[{d.title}]\n{d.content}" for d in found_docs
        )

        # Вызов реальной LLM через ProxyAPI
        result = call_llm(question=query.question, context=context_text)

        llm_output = {
            "answer": result["answer"],
            "confidence_score": result["confidence_score"],
            "sources_found": [d.title for d in found_docs],
            "needs_review": result["needs_review"],
            "review_reason": result["review_reason"],
            "out_of_scope": result["out_of_scope"],
        }

        if result["out_of_scope"]:
            query.status = "rejected"
        elif result["needs_review"]:
            query.status = "needs_review"
        else:
            query.status = "processed"
        db.commit()

    except Exception as e:
        status = "fail"
        error_msg = str(e)
        query.status = "error"
        db.commit()
        llm_output = {"error": f"Ошибка LLM: {str(e)}"}
        logger.error("Process error: query id=%d error=%s", query_id, e)

    duration_ms = (time.time() - start_time) * 1000

    audit_record = AuditRun(
        action=action,
        input_data=json.dumps({"query_id": query_id, "question": query.question}),
        output_data=json.dumps(llm_output),
        status=status,
        error=error_msg,
        duration_ms=round(duration_ms, 2),
    )
    db.add(audit_record)
    db.commit()

    logger.info(
        "Query processed: id=%d status=%s confidence=%.2f duration=%.1fms",
        query_id, query.status, llm_output.get("confidence_score", 0), duration_ms,
    )
    return {"query_id": query_id, "new_status": query.status, "ai_response": llm_output}
