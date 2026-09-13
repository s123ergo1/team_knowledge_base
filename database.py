from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./team_knowledge.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(Text)
    category = Column(String)


class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String)
    question = Column(Text)
    status = Column(String, default="new")  # new, processed, needs_review, resolved
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("queries.id"))
    reviewer_name = Column(String)
    correct_answer = Column(Text)
    comment = Column(Text)
    status = Column(String, default="pending")  # pending, approved

    query = relationship("Query", backref="reviews")


class ResolvedMemory(Base):
    __tablename__ = "resolved_memory"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("queries.id"))
    final_answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    query = relationship("Query", backref="resolved_memory")


class AuditRun(Base):
    __tablename__ = "audit_runs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String)
    input_data = Column(Text)   # JSON string
    output_data = Column(Text)  # JSON string
    status = Column(String)     # success, fail
    error = Column(String, nullable=True)
    duration_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)
