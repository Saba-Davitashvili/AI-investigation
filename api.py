from dotenv import load_dotenv
from demo_security import authorize_demo
import logging

logger = logging.getLogger(__name__)

from fastapi.responses import FileResponse

from uploaded_index import (
    UploadedIndex,
    UploadIndexError,
    search_all
)
from fastapi import Response

from document_store import (
    DuplicateDocumentError,
    DocumentCapacityError,
    delete_document,
    get_document,
    initialize_store,
    list_documents,
    replace_document,
    save_document
)
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError
)
from pydantic import BaseModel, Field, ValidationError

from investigator import InvestigationError, investigate

import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from qdrant_client import QdrantClient

from bm25_index import BM25Index
from hybrid_search import fuse_rankings
from config import BASE_DIRECTORY, MODEL_NAME

load_dotenv(BASE_DIRECTORY / ".env")
from search import tokenize
from semantic_search import search_semantic


@asynccontextmanager
async def lifespan(app):
    if os.getenv("STORAGE_BACKEND") == "cloud":
        from cloud_runtime import cloud_lifespan
        async with cloud_lifespan(app):
            yield
        return
    from sentence_transformers import SentenceTransformer
    directory = BASE_DIRECTORY / "data" / "corpus"

    manifest = json.loads(
        (directory / "index_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    if not manifest.get("complete"):
        raise RuntimeError("Corpus indexing is incomplete.")

    if manifest["configuration"]["model"] != MODEL_NAME:
        raise RuntimeError("Embedding model does not match index.")

    print("Loading corpus chunks...")

    with (directory / "chunks_fixed_token.jsonl").open(
        encoding="utf-8"
    ) as file:
        documents = [
            json.loads(line)
            for line in file
        ]

    if len(documents) != manifest["stored_chunks"]:
        raise RuntimeError("Chunk file count does not match index.")

    print("Building keyword index...")
    app.state.keyword_index = BM25Index(documents)

    print("Loading embedding model...")
    app.state.model = SentenceTransformer(
        MODEL_NAME,
        device="cpu"
    )

    client = QdrantClient(
        path=str(BASE_DIRECTORY / "indexes" / "qdrant")
    )

    try:
        collection = manifest["collection"]

        stored_count = client.count(
            collection_name=collection,
            exact=True
        ).count

        if stored_count != manifest["stored_chunks"]:
            raise RuntimeError("Vector count does not match manifest.")

        app.state.client = client
        app.state.collection = collection
        app.state.source_count = manifest["source_documents"]
        app.state.chunk_count = stored_count

        initialize_store()

        print("Indexing saved uploads...")
        app.state.upload_index = UploadedIndex(
            client,
            app.state.model
        )
        app.state.upload_index.refresh()

        yield

    finally:
        client.close()


app = FastAPI(
    title="AI Investigation Engine",
    lifespan=lifespan
)


@app.middleware("http")
async def demo_access(request: Request, call_next):
    if request.url.path == "/readyz" and request.method in {"GET", "HEAD"}:
        return await call_next(request)
    rejection = authorize_demo(request)
    if rejection is not None:
        return rejection
    return await call_next(request)


@app.get("/health")
def health(request: Request):
    state = request.app.state

    return {
        "status": "ok",
        "source_documents": state.source_count,
        "indexed_chunks": state.chunk_count,
        "collection": state.collection,
        "storage_backend": os.getenv("STORAGE_BACKEND", "local"),
        "embedding_backend": getattr(state, "embedding_backend", MODEL_NAME),
        "corpus_fingerprint": getattr(state, "corpus_fingerprint", None),
        "source_revision": os.getenv("RENDER_GIT_COMMIT")
    }


@app.get("/search")
def search(
    request: Request,
    q: str = Query(min_length=1, max_length=500),
    mode: Literal["keyword", "semantic", "hybrid"] = "semantic",
    limit: int = Query(default=5, ge=1, le=20)
):
    if not tokenize(q):
        raise HTTPException(
            status_code=422,
            detail="Query must contain at least one word or number."
        )

    try:
        results = search_all(
            request.app.state,
            q,
            mode=mode,
            limit=limit
        )
    except UploadIndexError:
        raise HTTPException(
            status_code=503,
            detail="Upload search needs reindexing. Restart the API."
        ) from None

    return {
        "query": q,
        "mode": mode,
        "returned_count": len(results),
        "results": results
    }
class InvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
@app.post("/investigate")
def investigate_question(
    body: InvestigationRequest,
    request: Request
):
    question = body.question.strip()

    if not tokenize(question):
        raise HTTPException(
            status_code=422,
            detail="Question must contain at least one word or number."
        )

    state = request.app.state

    def retrieve(query, limit=3):
        return search_all(
            state,
            query,
            mode="hybrid",
            limit=limit
        )

    try:
        return investigate(question, retrieve)

    except UploadIndexError:
        raise HTTPException(status_code=503, detail="Upload search is unavailable. Restart the API to rebuild it.") from None

    except AuthenticationError:
        raise HTTPException(
            status_code=503,
            detail="The LLM provider credentials need attention."
        ) from None

    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="LLM rate limit reached. Try again later."
        ) from None

    except APITimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The LLM provider timed out."
        ) from None

    except APIConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to the LLM provider."
        ) from None

    except APIStatusError:
        logger.exception("LLM provider rejected the investigation")
        raise HTTPException(
            status_code=502,
            detail="The LLM provider could not complete the request."
        ) from None

    except (InvestigationError, ValidationError):
        logger.exception("Investigation response validation failed")

        raise HTTPException(
            status_code=502,
            detail=(
                "The investigation could not produce a valid, "
                "source-checked response."
            )
        ) from None
    
from fastapi import UploadFile

from document_reader import (
    DocumentReadError,
    MAX_FILE_BYTES,
    read_document
)
def refresh_upload_search(request):
    try:
        request.app.state.upload_index.refresh()
    except UploadIndexError:
        raise HTTPException(
            status_code=503,
            detail={
                "storage_change_saved": True,
                "message": (
                    "Document storage changed, but indexing failed. "
                    "Restart the API to rebuild upload search."
                )
            }
        ) from None

@app.post("/documents/preview")
def preview_document(file: UploadFile):
    try:
        content = file.file.read(MAX_FILE_BYTES + 1)

        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Maximum file size is 10 MiB."
            )

        document = read_document(
            file.filename or "",
            content
        )

        return {
            "filename": document["filename"],
            "format": document["format"],
            "character_count": len(document["text"]),
            "page_count": document["page_count"],
            "pages": document["pages"],
            "preview": document["text"][:2000],
            "saved": False
        }

    except DocumentCapacityError as error:
        raise HTTPException(status_code=413, detail=str(error)) from None

    except DocumentReadError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from None

    finally:
        file.file.close()

@app.post("/documents")
def upload_document(
    response: Response,
    file: UploadFile,
    request: Request
):
    try:
        content = file.file.read(MAX_FILE_BYTES + 1)

        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Maximum file size is 10 MiB."
            )

        parsed = read_document(
            file.filename or "",
            content
        )

        with request.app.state.upload_index.lock:
            result = save_document(parsed, content)
            refresh_upload_search(request)

        response.status_code = (
            200 if result["duplicate"] else 201
        )

        return {
            **result,
            "saved": True,
            "indexed": True
        }

    except DocumentCapacityError as error:
        raise HTTPException(status_code=413, detail=str(error)) from None

    except DocumentReadError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from None

    finally:
        file.file.close()


@app.get("/documents")
def documents_list():
    documents = list_documents()

    return {
        "count": len(documents),
        "documents": documents
    }


@app.get("/documents/{document_id}")
def document_detail(document_id: str):
    document = get_document(document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    return document

@app.put("/documents/{document_id}")
def update_document(
    document_id: str,
    file: UploadFile,
    request: Request
):
    try:
        if get_document(document_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found."
            )

        content = file.file.read(MAX_FILE_BYTES + 1)

        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Maximum file size is 10 MiB."
            )

        parsed = read_document(
            file.filename or "",
            content
        )

        with request.app.state.upload_index.lock:
            document = replace_document(
                document_id,
                parsed,
                content
            )

            if document is None:
                raise HTTPException(
                    status_code=404,
                    detail="Document not found."
                )

            refresh_upload_search(request)

        return {
            "document": document,
            "saved": True,
            "indexed": True
        }

    except DocumentCapacityError as error:
        raise HTTPException(status_code=413, detail=str(error)) from None

    except DocumentReadError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from None

    except DuplicateDocumentError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from None

    finally:
        file.file.close()


@app.delete("/documents/{document_id}", status_code=204)
def remove_document(document_id: str, request: Request):
    with request.app.state.upload_index.lock:
        if not delete_document(document_id):
            raise HTTPException(
                status_code=404,
                detail="Document not found."
            )

        refresh_upload_search(request)

    return Response(status_code=204)

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIRECTORY / "ui.html")

@app.get("/readyz", include_in_schema=False)
def readiness():
    # Startup cannot finish until the configured index is verified. No metadata.
    return {"status": "ok"}
