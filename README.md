# FastAPI Knowledge RAG Service

This repository now includes:

- FastAPI + Poetry project setup
- SQLAlchemy + Alembic migrations
- PostgreSQL-backed knowledge + metadata storage
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

- `SQLALCHEMY_DATABASE_URI`
- `GEMINI_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX_NAME`

> Note: This project currently uses **both** PostgreSQL and Pinecone.
> Pinecone stores vectors, while PostgreSQL stores knowledge records/chunks and IDs used by CRUD and source retrieval.
> If you want a Pinecone-only architecture, code changes are required (it is not yet supported out of the box).

## 3) Run PostgreSQL locally

Example with Docker:

```bash
docker run --name rag-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=knowledge_rag -p 5432:5432 -d postgres:16
```

## 4) Apply migrations

```bash
poetry run alembic upgrade head
```

## 5) Run app

```bash
poetry run python main.py
```

Swagger docs: `http://127.0.0.1:8000/docs`

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
