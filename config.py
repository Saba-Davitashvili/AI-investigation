from pathlib import Path

BASE_DIRECTORY = Path(__file__).resolve().parent
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "hotpot_sample"

def embedding_dimension(model):
    method = getattr(model, "get_embedding_dimension", None)
    return method() if method else model.get_sentence_embedding_dimension()
