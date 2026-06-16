from contextlib import asynccontextmanager
import gc
import logging
import os
import time
from typing import Optional

import chromadb
from chromadb.utils.batch_utils import create_batches
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import APITimeoutError
from langchain.tools import tool
from langchain_chroma import Chroma
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

# CONFIGURATION
load_dotenv()
os.environ["LANGCHAIN_TRACING_V2"] = "false"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
COLLECTION_NAME = "soccer"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "2"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is required")

GROQ_HF_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
if not GROQ_HF_TOKEN:
    raise ValueError("HUGGINGFACEHUB_API_TOKEN environment variable is required")

# Global external embedding engine - Outsourced to Hugging Face infrastructure
embedder = HuggingFaceEndpointEmbeddings(
    model="sentence-transformers/all-MiniLM-L6-v2",
    task="feature-extraction",
    huggingfacehub_api_token=GROQ_HF_TOKEN
)

# GLOBAL STATE
_app_state = {
    "llm": None,
    "vectorstore": None,
    "agent": None,
    "ready": False,
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    try:
        logger.info("Starting FootballIQ application...")

        logger.info(f"Connecting to ChromaDB at {CHROMA_DB_PATH}...")
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        existing_collections = [c.name for c in chroma_client.list_collections()]

        if COLLECTION_NAME not in existing_collections:
            logger.info(f"Collection '{COLLECTION_NAME}' missing. Starting raw compilation...")

            files = [
                "data/ea_fc26_players.csv",
                "data/ea_fc26_outfield.csv",
                "data/ea_fc26_goalkeepers.csv",
            ]

            all_data = []
            for file_path in files:
                try:
                    loader = CSVLoader(file_path=file_path)
                    all_data.extend(loader.load())
                    logger.info(f"Loaded {file_path}")
                except FileNotFoundError:
                    logger.warning(f"File missing: {file_path}")

            if not all_data:
                raise RuntimeError("Critical: No source database CSVs discovered.")

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
            )
            docs = splitter.split_documents(all_data)
            sentences = [doc.page_content for doc in docs]

            collection = chroma_client.create_collection(COLLECTION_NAME)

            logger.info("Generating embeddings via Hugging Face Inference API...")
            embeddings = embedder.embed_documents(sentences)

            batches = create_batches(
                api=chroma_client,
                embeddings=embeddings,
                ids=[str(i) for i in range(len(embeddings))],
                documents=sentences,
            )
            for batch in batches:
                ids_batch, embeddings_batch, _, documents_batch = batch
                collection.add(
                    ids=ids_batch,
                    embeddings=embeddings_batch,
                    documents=documents_batch,
                )
            logger.info("Ingestion completed smoothly.")

        _app_state["vectorstore"] = Chroma(
            client=chroma_client,
            collection_name=COLLECTION_NAME,
            embedding_function=embedder,
        )

        logger.info("Initializing remote LLM links...")
        _app_state["llm"] = ChatGroq(
            api_key=GROQ_API_KEY,
            model=LLM_MODEL,
            temperature=0,
            timeout=LLM_TIMEOUT,
            max_retries=2,
        )

        @tool(response_format="content_and_artifact")
        def retrieve_context(query: str):
            """Retrieve information to help answer a query about EA FC player ratings."""
            try:
                retrieved_docs = _app_state["vectorstore"].similarity_search(
                    query, k=TOP_K_RESULTS
                )
                serialized = "\n\n".join(
                    f"Source: {doc.metadata}\nContent: {doc.page_content}"
                    for doc in retrieved_docs
                )
                return serialized, retrieved_docs
            except Exception as e:
                logger.error(f"Error extracting contexts: {str(e)}")
                raise

        system_message = SystemMessage(
            content=("""
                    You are 'FootballIQ', the ultimate football banter and EA Sports FC ratings guru. 
                    Your job is to answer user queries about player ratings, stats, and comparisons with extreme energy, creative flair, and authentic football fan culture.

                    Rules for your responses:
                    1. NEVER be boring. Use punchy, engaging language.
                    2. Use modern football terminology and community slang (e.g., 'pace merchant', 'baller', 'cooked', 'clutch', '80+ club').
                    3. If a player has an iconic stat (like 95 Pace or 40 Defending), dramatize it creatively.
                    4. Always wrap up your answer with a hot take or a highly engaging question to keep the user typing.
                    5. Use emojis strategically to break up text and look like a modern sports app interface.
                """)
        )

        _app_state["agent"] = create_react_agent(
            _app_state["llm"], [retrieve_context], prompt=system_message
        )

        _app_state["ready"] = True
        logger.info("✅ FootballIQ application started successfully!")

    except Exception as e:
        logger.error(f"❌ Initialization fault: {str(e)}", exc_info=True)
        _app_state["ready"] = False
        raise

    yield

    logger.info("Shutting down FootballIQ application...")
    _app_state["ready"] = False
    _app_state["agent"] = None
    _app_state["vectorstore"] = None
    _app_state["llm"] = None
    gc.collect()
    logger.info("Shutdown sequence complete.")


app = FastAPI(
    title="FootballIQ",
    description="Conversational RAG system for EA FC 26 player stats",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     
    allow_credentials=False, 
    allow_methods=["*"],     
    allow_headers=["*"],     
)


class QueryRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=1000, description="User query about EA FC players"
    )

class QueryResponse(BaseModel):
    response: str
    query: str
    timestamp: float

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: float

class HealthResponse(BaseModel):
    status: str
    ready: bool
    timestamp: float


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests and responses, bypassing options preflights."""
    if request.method == "OPTIONS":
        return await call_next(request)

    start_time = time.time()
    request_id = request.headers.get("x-request-id", "unknown")

    logger.info(f"[{request_id}] {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"[{request_id}] Completed in {process_time:.2f}s | Status: {response.status_code}"
        )
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Request failed: {str(e)}", exc_info=True)
        raise

@app.post("/ask", response_model=QueryResponse)
async def ask(request: QueryRequest):
    """Query the football AI assistant."""
    try:
        if not _app_state["ready"]:
            logger.warning("Request received but app is not ready")
            raise HTTPException(
                status_code=503, detail="Application is still initializing"
            )

        logger.info(f"Processing query: {request.query[:100]}...")

        try:
            result = _app_state["agent"].invoke(
                {"messages": [HumanMessage(content=request.query)]}
            )
            response_text = result["messages"][-1].content

            logger.info("Query processed successfully")
            return QueryResponse(
                response=response_text,
                query=request.query,
                timestamp=time.time(),
            )
        except APITimeoutError as e:
            logger.error(f"LLM timeout: {str(e)}")
            raise HTTPException(
                status_code=504, detail="LLM request timed out. Please try again."
            )
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500, detail="Failed to process query. Please try again."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /ask: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy" if _app_state["ready"] else "initializing",
        ready=_app_state["ready"],
        timestamp=time.time(),
    )


@app.get("/")
async def root():
    return {
        "name": "FootballIQ",
        "description": "Conversational RAG system for EA FC 26 player stats",
        "version": "1.0.0",
        "endpoints": {
            "ask": {"path": "/ask", "method": "POST"},
            "health": {"path": "/health", "method": "GET"},
            "docs": {"path": "/docs", "method": "GET"},
        },
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail or "An error occurred",
            detail=str(exc),
            timestamp=time.time(),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail="An unexpected error occurred",
            timestamp=time.time(),
        ).model_dump(),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )