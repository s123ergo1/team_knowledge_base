"""
Извлечение текста из файлов PDF, DOCX и TXT.
"""
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

SUPPORTED = (".pdf", ".docx", ".txt")


def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """
    Извлекает текст из файла.
    Возвращает строку с текстом или строку с описанием ошибки, начинающуюся с '['.
    """
    name = filename.lower()

    try:
        if name.endswith(".txt"):
            return file_content.decode("utf-8", errors="ignore")

        elif name.endswith(".pdf"):
            import PyPDF2
            reader = PyPDF2.PdfReader(BytesIO(file_content))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            if not text:
                return "[PDF не содержит извлекаемого текста (возможно, сканированный документ)]"
            return text

        elif name.endswith(".docx"):
            import docx
            doc = docx.Document(BytesIO(file_content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)

        else:
            return f"[Неподдерживаемый формат: {filename}. Разрешены: {', '.join(SUPPORTED)}]"

    except Exception as e:
        logger.error("File extraction error: file=%s error=%s", filename, e)
        return f"[Ошибка чтения файла '{filename}': {e}]"
