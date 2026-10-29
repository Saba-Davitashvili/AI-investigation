"""Small web runtime: ONNX model + Qdrant dense/sparse + PostgreSQL originals."""
import os
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

import cloud_storage as storage
from cloud_embeddings import BACKEND_ID, OnnxMiniLM
from cloud_search import corpus_statistics, document_sparse, query_sparse
from chunk_documents import chunk_document, validate_chunks
from config import embedding_dimension
from document_store import initialize_store, list_documents, get_document
from hybrid_search import fuse_rankings
from search import tokenize
from uploaded_index import UploadIndexError

UPLOAD_COLLECTION = "trace_uploads_cloud_v1"


def cloud_client():
    url, key = os.getenv("QDRANT_URL", ""), os.getenv("QDRANT_API_KEY", "")
    if not url.startswith("https://") or not key:
        raise RuntimeError("Set an HTTPS QDRANT_URL and QDRANT_API_KEY in the environment.")
    return QdrantClient(url=url, api_key=key, timeout=60, prefer_grpc=False)


def create_collection(client, name, dimension=384):
    client.create_collection(
        collection_name=name,
        vectors_config={"dense": models.VectorParams(size=dimension, distance=models.Distance.COSINE, on_disk=True)},
        sparse_vectors_config={"keyword": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=True))},
        on_disk_payload=True,
    )


def write_batch(client, name, model, batch, vocabulary, average_length):
    vectors = model.encode([f"{chunk['title']}\n{chunk['text']}" for chunk in batch], normalize_embeddings=True)
    points = [models.PointStruct(id=str(uuid5(NAMESPACE_URL, chunk["id"])),
                                vector={"dense": vector.tolist(), "keyword": document_sparse(chunk, vocabulary, average_length)},
                                payload=chunk) for chunk, vector in zip(batch, vectors)]
    if points:
        client.upsert(collection_name=name, points=points, wait=True)


class CloudUploads:
    def __init__(self, client, model):
        self.client, self.model = client, model
        self.lock = storage.SharedUploadLock()
        self.ready = False
        self.chunks = []

    def refresh(self):
        with self.lock:
            self.ready = False
            try:
                chunks = []
                for item in list_documents():
                    document = get_document(item["id"])
                    if document is None:
                        continue
                    source = {"id": f"{document['id']}:{document['version']}", "title": document["filename"],
                              "text": document["text"], "source": "uploaded_document", "config": "custom", "split": "custom"}
                    group = chunk_document(source, self.model.tokenizer, "fixed_token")
                    validate_chunks(group, [source], self.model)
                    for chunk in group:
                        chunk.update(parent_id=document["id"], version=document["version"], format=document["format"],
                                     page_numbers=[page["page_number"] for page in document["pages"]
                                                   if page["char_start"] < chunk["char_end"] and page["char_end"] > chunk["char_start"]])
                    chunks.extend(group)
                vocabulary, count, average = corpus_statistics(chunks)
                stats = {"chunk_count": count, "average_length": average, "backend": BACKEND_ID}
                storage.save_statistics(UPLOAD_COLLECTION, stats, vocabulary)
                if self.client.collection_exists(UPLOAD_COLLECTION):
                    self.client.delete_collection(UPLOAD_COLLECTION)
                create_collection(self.client, UPLOAD_COLLECTION, embedding_dimension(self.model))
                for start in range(0, len(chunks), 16):
                    write_batch(self.client, UPLOAD_COLLECTION, self.model, chunks[start:start + 16], vocabulary, average)
                if self.client.count(UPLOAD_COLLECTION, exact=True).count != count:
                    raise RuntimeError("Upload vector count mismatch.")
                storage.mark_complete(UPLOAD_COLLECTION)
                self.chunks = chunks
                self.ready = True
            except Exception as error:
                raise UploadIndexError("Cloud upload indexing failed; persisted documents can be rebuilt on restart.") from error


def ranked(client, name, vector, using):
    if using == "keyword" and not vector.indices:
        return []
    points = client.query_points(collection_name=name, query=vector, using=using,
                                 limit=20, with_payload=True).points
    return [{"document": point.payload, "score": point.score} for point in points]


def cloud_search_all(state, query, mode="hybrid", limit=5):
    try:
        with state.upload_index.lock:
            if not state.upload_index.ready:
                raise UploadIndexError("Cloud upload index is unavailable.")
            names = [state.collection]
            if state.upload_index.chunks:
                names.append(UPLOAD_COLLECTION)
            keyword, semantic = [], []
            if mode in {"keyword", "hybrid"}:
                rankings = []
                words = tokenize(query)
                for name in names:
                    meta = storage.metadata(name)
                    vocabulary = storage.lookup_terms(name, words)
                    rankings.append(ranked(state.client, name, query_sparse(query, vocabulary, meta["chunk_count"]), "keyword"))
                keyword = fuse_rankings(rankings, limit=20)
            if mode in {"semantic", "hybrid"}:
                vector = state.model.encode(query).tolist()
                for name in names:
                    semantic.extend(ranked(state.client, name, vector, "dense"))
                semantic = sorted(semantic, key=lambda item: (-item["score"], item["document"]["id"]))[:20]
            if mode == "keyword":
                return keyword[:limit]
            if mode == "semantic":
                return semantic[:limit]
            return fuse_rankings([keyword, semantic], limit=limit)
    except UploadIndexError:
        raise
    except Exception as error:
        raise UploadIndexError("Cloud search dependencies are unavailable.") from error


@asynccontextmanager
async def cloud_lifespan(app):
    initialize_store()
    storage.initialize_search_store()
    name = os.getenv("QDRANT_CORPUS_COLLECTION", "trace_corpus_cloud_v1")
    manifest = storage.metadata(name)
    if manifest.get("backend") != BACKEND_ID:
        raise RuntimeError("Cloud model/index mismatch. Seed with the pinned cloud backend.")
    if manifest.get("source_documents", 0) < 50000:
        raise RuntimeError("Cloud corpus has fewer than the required 50,000 documents.")
    client = cloud_client()
    try:
        if client.count(name, exact=True).count != manifest["chunk_count"]:
            raise RuntimeError("Cloud vector count does not match corpus metadata.")
        dense = client.get_collection(name).config.params.vectors
        if not isinstance(dense, dict) or "dense" not in dense or dense["dense"].size != 384:
            raise RuntimeError("Cloud dense vector configuration is invalid.")
        app.state.client, app.state.collection = client, name
        app.state.source_count = manifest["source_documents"]
        app.state.chunk_count = manifest["chunk_count"]
        app.state.embedding_backend = BACKEND_ID
        app.state.corpus_fingerprint = manifest["input_fingerprint"]
        app.state.model = OnnxMiniLM(os.getenv("ONNX_MODEL_DIRECTORY") or None)
        app.state.upload_index = CloudUploads(client, app.state.model)
        app.state.upload_index.refresh()
        yield
    finally:
        client.close()
