# FootballIQ ⚽

> Conversational RAG system for EA FC 26 player stats and profiles.

![Python](https://img.shields.io/badge/Python-3.13-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green) ![LangChain](https://img.shields.io/badge/LangChain-0.3+-orange) ![ChromaDB](https://img.shields.io/badge/ChromaDB-0.6+-red) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Demo

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Salah pace and dribbling in EA FC 26?"}'
```

```json
{
  "response": "Mohamed Salah's pace (PAC) is 89 and his dribbling (DRI) is 87 in EA FC 26."
}
```

---

## Overview

FootballIQ is a retrieval-augmented generation (RAG) system built over EA FC 26 player data. Instead of relying on an LLM's training knowledge, it embeds 16,000+ player profiles into a local vector database and retrieves the most relevant chunks before generating an answer — making responses grounded in real data, not hallucination.

The system exposes a REST API via FastAPI, uses a LangGraph ReAct agent to autonomously decide when to query the vector store, and runs entirely locally with no external database dependencies.

---

## Architecture

```
User Query (POST /ask)
        │
        ▼
  FastAPI Endpoint
        │
        ▼
  LangGraph ReAct Agent
        │
        ├──► Decides to use retrieve_context tool
        │
        ▼
  ChromaDB Similarity Search
  (all-MiniLM-L6-v2 embeddings, k=2)
        │
        ▼
  Top-K Relevant Player Chunks
        │
        ▼
  Groq LLM (qwen/qwen3-32b)
  Prompt: system message + retrieved context + user query
        │
        ▼
  Grounded Answer → JSON Response
```

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| API Framework | FastAPI | Async support, automatic docs at `/docs`, Pydantic validation |
| Agent | LangGraph ReAct | Autonomous tool-use decisions, structured reasoning loop |
| Orchestration | LangChain | Unified interface for embeddings, vector stores, and LLMs |
| Vector Database | ChromaDB | Local, persistent, no external service needed |
| Embeddings | all-MiniLM-L6-v2 | Fast, lightweight, 384-dim, runs on CPU |
| LLM | Groq · qwen/qwen3-32b | Free tier, low latency inference |
| Data | pandas + CSVLoader | Structured player profile ingestion |
| Runtime | Python 3.13 | |

---

## Project Structure

```
rag_qa_football/
│
├── api.py                  # FastAPI app — endpoints, agent, retrieval tool
├── starting.ipynb          # Data pipeline — ingest, chunk, embed, store
│
├── data/
│   ├── ea_fc26_players.csv         # Outfield player profiles
│   ├── ea_fc26_outfield.csv        # Outfield stats
│   └── ea_fc26_goalkeepers.csv     # Goalkeeper profiles
│
├── chroma_db/              # Persisted ChromaDB vector store (auto-generated)
│
├── .env                    # API keys — never commit this
├── .gitignore
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- conda or venv
- A free [Groq API key](https://console.groq.com/keys)

### 1. Clone the repository

```bash
git clone https://github.com/KishoharS/footballiq.git
cd footballiq
```

### 2. Create and activate a virtual environment

```bash
conda create -n rag_qa_football python=3.13
conda activate rag_qa_football
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the root directory:

```
GROQ_API_KEY=your_groq_api_key_here
LANGCHAIN_TRACING_V2=false
```

### 5. Build the vector store

Run `starting.ipynb` end to end. This will:
- Load the EA FC 26 player CSVs
- Split documents into chunks
- Generate embeddings using `all-MiniLM-L6-v2`
- Persist all 16,254 vectors into ChromaDB at `./chroma_db`

This step only needs to be done once. The vector store persists across restarts.

### 6. Start the API server

```bash
uvicorn api:app --reload
```

The server runs at `http://localhost:8000`.

---

## Usage

### Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Who has better defending — Rodri or Casemiro?"}'
```

### Health check

```bash
curl http://localhost:8000/health
```

### Interactive API docs

Open `http://localhost:8000/docs` in your browser for FastAPI's auto-generated Swagger UI.

---

## API Reference

### `POST /ask`

Ask a natural language question about EA FC 26 player data.

**Request body:**

```json
{
  "query": "string"
}
```

**Response:**

```json
{
  "response": "string"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Mbappe overall rating?"}'
```

```json
{
  "response": "Kylian Mbappé has an overall rating of 91 in EA FC 26..."
}
```

---

### `GET /health`

Check if the service is running.

**Response:**

```json
{
  "status": "ok"
}
```

---

## Known Limitations

- **Only EA FC 26 data** — questions about real-world match stats, injuries, or transfer news are outside the system's knowledge.
- **In-context retrieval only** — the agent retrieves `k=2` chunks per query. Complex multi-player comparisons may miss relevant context.
- **No conversation memory** — each request is stateless. The agent does not remember previous questions in the same session.
- **Local only** — the server runs on `localhost`. Deployment to a public URL requires additional configuration (CORS, hosting).
- **Response latency** — the ReAct agent makes 2 LLM calls per query (one to decide tool use, one to generate the answer), typically 3–6 seconds on Groq's free tier.

---

## Roadmap

- [ ] Load goalkeeper and outfield CSVs into ChromaDB (currently only `ea_fc26_players.csv` is indexed)
- [ ] Add conversation memory so multi-turn queries work correctly
- [ ] Increase `k` and experiment with re-ranking for better retrieval quality
- [ ] Evaluate answer quality using RAGAS
- [ ] Deploy FastAPI to Railway or Render with a public endpoint
- [ ] Connect the FootballIQ webpage demo to the live API

---

## License

MIT © 2026 Kishohar S.
