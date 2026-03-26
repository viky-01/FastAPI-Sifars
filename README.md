# FastAPI Knowledge RAG Service

This repository now includes:

- FastAPI + Poetry project setup
- SQLAlchemy + Alembic migrations
- Optional PostgreSQL-backed knowledge + metadata storage
- CRUD APIs for knowledge records
- Gemini + Pinecone powered `/ask` RAG endpoint (Pinecone is the vector store)

## Project Structure

```text
src/
  app.py
  configs/
  entities/
    knowledge/
    audit_log/
    base/
  middlewares/
  migrations/
```

## 1) Install dependencies

```bash
poetry install
```

## 2) Configure environment

Copy and edit `.env`:

```bash
cp .env.example .env
```

Required variables:

- `GEMINI_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX_NAME`

Optional variables:

- `SQLALCHEMY_DATABASE_URI` (required only if you want SQL-backed CRUD and migrations)
- `PINECONE_ONLY_MODE=true` (forces Pinecone-only behavior even if DB URL is set)

## 3) (Optional) Run PostgreSQL locally

Example with Docker:

```bash
docker run --name rag-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=knowledge_rag -p 5432:5432 -d postgres:16
```

## 4) (Optional) Apply migrations

```bash
poetry run alembic upgrade head
```

## 5) Run app

```bash
poetry run python main.py
```

Swagger docs: `http://127.0.0.1:8000/docs`

### Pinecone-only mode notes

- If `SQLALCHEMY_DATABASE_URI` is not set, app startup skips DB migrations automatically.
- In Pinecone-only mode, knowledge chunks and retrieval sources are read directly from Pinecone metadata.
- For best results in Pinecone-only mode, create/patch knowledge through this service so metadata contains `title` and `chunk_text`.

## API Endpoints

### Knowledge CRUD

- `POST /api/v1/knowledge/`
- `GET /api/v1/knowledge/`
- `GET /api/v1/knowledge/{id}`
- `PATCH /api/v1/knowledge/{id}`
- `PUT /api/v1/knowledge/{id}`
- `DELETE /api/v1/knowledge/{id}`

Pagination on list:

- `page` (default `1`)
- `page_size` (default `10`)

### RAG

- `POST /api/v1/knowledge/ask`

Request:

```json
{
  "question": "What are the key points from my stored notes?",
  "top_k": 5
}
```

Response returns:

- `answer`
- `sources` (matching chunk references)
