"""Data service: PostgreSQL persistence for the integrator."""
import os
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from sqlalchemy import URL, create_engine, MetaData, Table, Column, String, Float, select, insert, update, text
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.exc import SQLAlchemyError
from .models import CreditApplication, CreditApplicationCreate, CreditApplicationStatusUpdate
from .telemetry import configure, tracer, logger, flush

database_url = os.getenv("DATABASE_URL") or URL.create(
    "postgresql+psycopg", username=os.getenv("DATABASE_USER", "lab"),
    password=os.environ.get("DATABASE_PASSWORD"), database=os.getenv("DATABASE_NAME", "credits"),
    host=os.getenv("DATABASE_HOST", "postgres"),
    port=int(os.getenv("DATABASE_PORT", "5432")),
    query={"sslmode": os.getenv("DATABASE_SSLMODE", "verify-full"),
           **({"sslrootcert": os.environ["DATABASE_SSLROOTCERT"]} if os.getenv("DATABASE_SSLROOTCERT") else {})})
engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
metadata = MetaData()
credits = Table("credit_applications", metadata,
    Column("application_id", String(36), primary_key=True),
    Column("customer_name", String, nullable=False),
    Column("document_number", String, nullable=False),
    Column("requested_amount", Float, nullable=False),
    Column("status", String, nullable=False))

@asynccontextmanager
async def lifespan(app):
    metadata.create_all(engine)
    yield
    flush()
    engine.dispose()

app = FastAPI(title="Credit data service", lifespan=lifespan)
configure(app, engine)
Instrumentator().instrument(app).expose(app)

@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request, error):
    from fastapi.responses import JSONResponse
    logger.error("credit.database.unavailable")
    return JSONResponse(status_code=503, content={"detail": "Credit storage unavailable"})

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

@app.post("/credit-applications", response_model=CreditApplication, status_code=201)
def create(data: CreditApplicationCreate):
    with tracer.start_as_current_span("credit.persist"):
        row = dict(data.model_dump(), application_id=str(uuid4()), status="PENDING")
        with engine.begin() as conn:
            conn.execute(insert(credits).values(**row))
        logger.info("credit.persisted")
        return row

@app.get("/credit-applications", response_model=list[CreditApplication])
def listing():
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(credits)).mappings()]

@app.get("/credit-applications/{application_id}", response_model=CreditApplication)
def get(application_id: str):
    with engine.connect() as conn:
        row = conn.execute(select(credits).where(credits.c.application_id == application_id)).mappings().first()
    if row is None:
        raise HTTPException(404, "Credit application not found")
    return dict(row)

@app.put("/credit-applications/{application_id}/status", response_model=CreditApplication)
def status(application_id: str, data: CreditApplicationStatusUpdate):
    with tracer.start_as_current_span("credit.status_update"):
        with engine.begin() as conn:
            row = conn.execute(update(credits).where(credits.c.application_id == application_id)
                .values(status=data.status.value).returning(credits)).mappings().first()
        if row is None:
            raise HTTPException(404, "Credit application not found")
        logger.info("credit.status.updated")
        return dict(row)
