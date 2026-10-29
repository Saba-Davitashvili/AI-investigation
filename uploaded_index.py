import os
from config import embedding_dimension
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import models

from bm25_index import BM25Index
from chunk_documents import chunk_document, validate_chunks
from document_store import get_document, list_documents
from hybrid_search import fuse_rankings
from semantic_search import search_semantic


COLLECTION = "uploaded_documents_v1"


class UploadIndexError(Exception):
    pass


class UploadedIndex:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.lock = RLock()
        self.ready = False
        self.chunks = []
        self.keyword_index = BM25Index([])

    def refresh(self):
        with self.lock:
            self.ready = False

            try:
                chunks = []

                for metadata in list_documents():
                    document = get_document(metadata["id"])

                    if document is None:
                        continue

                    source = {
                        "id": (
                            f"{document['id']}:"
                            f"{document['version']}"
                        ),
                        "title": document["filename"],
                        "text": document["text"],
                        "source": "uploaded_document",
                        "config": "custom",
                        "split": "custom"
                    }

                    document_chunks = chunk_document(
                        source,
                        self.model.tokenizer,
                        "fixed_token"
                    )

                    validate_chunks(
                        document_chunks,
                        [source],
                        self.model
                    )

                    for chunk in document_chunks:
                        chunk["parent_id"] = document["id"]
                        chunk["version"] = document["version"]
                        chunk["format"] = document["format"]

                        chunk["page_numbers"] = [
                            page["page_number"]
                            for page in document["pages"]
                            if (
                                page["char_start"] < chunk["char_end"]
                                and page["char_end"] > chunk["char_start"]
                            )
                        ]

                    chunks.extend(document_chunks)

                if self.client.collection_exists(COLLECTION):
                    self.client.delete_collection(COLLECTION)

                self.client.create_collection(
                    collection_name=COLLECTION,
                    vectors_config=models.VectorParams(
                        size=embedding_dimension(self.model),
                        distance=models.Distance.COSINE
                    )
                )

                for start in range(0, len(chunks), 32):
                    batch = chunks[start:start + 32]

                    vectors = self.model.encode(
                        [
                            f"{chunk['title']}\n{chunk['text']}"
                            for chunk in batch
                        ],
                        normalize_embeddings=True
                    )

                    self.client.upsert(
                        collection_name=COLLECTION,
                        points=[
                            models.PointStruct(
                                id=str(
                                    uuid5(NAMESPACE_URL, chunk["id"])
                                ),
                                vector=vector.tolist(),
                                payload=chunk
                            )
                            for chunk, vector in zip(batch, vectors)
                        ],
                        wait=True
                    )

                self.chunks = chunks
                self.keyword_index = BM25Index(chunks)
                self.ready = True

            except Exception as error:
                raise UploadIndexError(
                    "Uploaded-document indexing failed."
                ) from error


def search_all(state, query, mode="hybrid", limit=5):
    if os.getenv("STORAGE_BACKEND") == "cloud":
        from cloud_runtime import cloud_search_all
        return cloud_search_all(state, query, mode=mode, limit=limit)
    uploads = state.upload_index

    with uploads.lock:
        if not uploads.ready:
            raise UploadIndexError(
                "Uploaded-document search is unavailable."
            )

        keyword = []
        semantic = []

        if mode in {"keyword", "hybrid"}:
            corpus_keyword = state.keyword_index.search(
                query, limit=20
            )
            upload_keyword = uploads.keyword_index.search(
                query, limit=20
            )

            keyword = fuse_rankings(
                [corpus_keyword, upload_keyword],
                limit=20
            )

        if mode in {"semantic", "hybrid"}:
            semantic = search_semantic(
                query,
                state.model,
                state.client,
                limit=20,
                collection_name=state.collection
            )

            if uploads.chunks:
                semantic.extend(
                    search_semantic(
                        query,
                        state.model,
                        state.client,
                        limit=20,
                        collection_name=COLLECTION
                    )
                )

            semantic = sorted(
                semantic,
                key=lambda result: (
                    -result["score"],
                    result["document"]["id"]
                )
            )[:20]

        if mode == "keyword":
            return keyword[:limit]

        if mode == "semantic":
            return semantic[:limit]

        return fuse_rankings(
            [keyword, semantic],
            limit=limit
        )