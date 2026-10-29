import hashlib
import json
import re
from bisect import bisect_right


from config import BASE_DIRECTORY, MODEL_NAME


MAX_TOKENS = 160
OVERLAP = 32


def chunk_document(document, tokenizer, strategy):
    if strategy not in {"fixed_token", "sentence_boundary"}:
        raise ValueError(f"Unknown strategy: {strategy}")

    text = document["text"]

    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False
    )

    offsets = encoded["offset_mapping"]

    if not offsets:
        return []

    sentence_ends = [
        match.end()
        for match in re.finditer(r'[.!?](?=\s|$)', text)
    ]

    chunks = []
    start = 0

    while start < len(offsets):
        end = min(start + MAX_TOKENS, len(offsets))

        if strategy == "sentence_boundary" and end < len(offsets):
            minimum_end = start + MAX_TOKENS // 2

            for candidate in range(end, minimum_end - 1, -1):
                character_end = offsets[candidate - 1][1]
                previous_end = bisect_right(
                    sentence_ends, character_end
                ) - 1

                if (
                    previous_end >= 0
                    and sentence_ends[previous_end] == character_end
                ):
                    end = candidate
                    break

        character_start = offsets[start][0]
        character_end = offsets[end - 1][1]
        chunk_text = text[character_start:character_end]

        identity = (
            f"{document['id']}:{strategy}:"
            f"{MAX_TOKENS}:{OVERLAP}:"
            f"{character_start}:{character_end}"
        )

        chunk_id = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()

        chunks.append({
            "id": chunk_id,
            "parent_id": document["id"],
            "title": document["title"],
            "text": chunk_text,
            "source": document["source"],
            "config": document["config"],
            "split": document["split"],
            "strategy": strategy,
            "char_start": character_start,
            "char_end": character_end
        })

        if end == len(offsets):
            break

        start = end - OVERLAP

    return chunks


def validate_chunks(chunks, documents, model):
    originals = {
        document["id"]: document
        for document in documents
    }

    for chunk in chunks:
        parent = originals[chunk["parent_id"]]

        original_text = parent["text"][
            chunk["char_start"]:chunk["char_end"]
        ]

        if chunk["text"] != original_text:
            raise ValueError("Chunk does not match its source.")

        embedding_text = f"{chunk['title']}\n{chunk['text']}"

        token_count = len(
            model.tokenizer(
                embedding_text,
                add_special_tokens=True,
                truncation=False
            )["input_ids"]
        )

        if token_count > model.max_seq_length:
            raise ValueError(
                f"Chunk exceeds model limit: "
                f"{token_count} > {model.max_seq_length}"
            )

    represented_parents = {
        chunk["parent_id"]
        for chunk in chunks
    }

    expected_parents = {
        document["id"]
        for document in documents
        if document["text"].strip()
    }

    if represented_parents != expected_parents:
        raise ValueError("Some source documents have no chunks.")


def main():
    from sentence_transformers import SentenceTransformer
    data_directory = BASE_DIRECTORY / "data"

    documents = json.loads(
        (data_directory / "sample_documents.json").read_text(
            encoding="utf-8"
        )
    )

    model = SentenceTransformer(MODEL_NAME, device="cpu")

    for strategy in ["fixed_token", "sentence_boundary"]:
        chunks = []

        for document in documents:
            chunks.extend(
                chunk_document(
                    document,
                    model.tokenizer,
                    strategy
                )
            )

        validate_chunks(chunks, documents, model)

        output_path = data_directory / f"chunks_{strategy}.json"

        output_path.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(
            f"{strategy}: {len(documents)} documents "
            f"-> {len(chunks)} chunks"
        )
        print("Source and token-limit checks passed.")


if __name__ == "__main__":
    main()