"""CPU ONNX MiniLM adapter without PyTorch or Transformers imports.

Uses the model author's FP32 ONNX export, attention-mask mean pooling and L2
normalization. Cloud vectors must be seeded with this same pinned backend;
historical SentenceTransformers evaluations do not benchmark this adapter.
"""
from pathlib import Path
from threading import RLock

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_FILE = "onnx/model.onnx"
BACKEND_ID = f"{MODEL_ID}@{REVISION}:{MODEL_FILE}:mean-l2-v1"


class OnnxMiniLM:
    max_seq_length = 256

    def __init__(self, directory=None):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
        if directory is None:
            tokenizer_path = hf_hub_download(MODEL_ID, "tokenizer.json", revision=REVISION)
            model_path = hf_hub_download(MODEL_ID, MODEL_FILE, revision=REVISION)
        else:
            tokenizer_path = str(Path(directory) / "tokenizer.json")
            model_path = str(Path(directory) / "model.onnx")
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.no_padding()
        self._tokenizer.no_truncation()
        self._lock = RLock()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(model_path, sess_options=options, providers=["CPUExecutionProvider"])

    def get_embedding_dimension(self):
        return 384

    def tokenizer(self, text, add_special_tokens=True, **kwargs):
        with self._lock:
            encoded = self._tokenizer.encode(text, add_special_tokens=add_special_tokens)
        return {"input_ids": encoded.ids, "offset_mapping": encoded.offsets}

    def encode(self, texts, normalize_embeddings=True):
        import numpy as np
        single = isinstance(texts, str)
        texts = [texts] if single else texts
        outputs = []
        # Single-sample batches bound intermediate activation memory on a 512 MiB host.
        with self._lock:
            for text in texts:
                self._tokenizer.enable_truncation(max_length=self.max_seq_length)
                try:
                    encoded = self._tokenizer.encode(text)
                finally:
                    self._tokenizer.no_truncation()
                inputs = {"input_ids": np.array([encoded.ids], dtype=np.int64),
                          "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
                          "token_type_ids": np.array([encoded.type_ids], dtype=np.int64)}
                feed = {item.name: inputs[item.name] for item in self.session.get_inputs()}
                hidden = self.session.run(None, feed)[0]
                mask = inputs["attention_mask"][..., None]
                pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
                if normalize_embeddings:
                    pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
                outputs.append(pooled[0].astype(np.float32))
        result = np.array(outputs, dtype=np.float32).reshape((-1, 384))
        return result[0] if single else result


def main():
    model = OnnxMiniLM()
    vectors = model.encode(["The payment request timed out.", "The payment request timed out.", "A cat sleeps."])
    import resource
    print({"shape": list(vectors.shape), "identical_cosine": float(vectors[0] @ vectors[1]),
           "unrelated_cosine": float(vectors[0] @ vectors[2]),
           "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)})


if __name__ == "__main__":
    main()
