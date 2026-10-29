"""Container entrypoint. Dataset bootstrap is explicit and runs before serving."""
import os

from dotenv import load_dotenv

from config import BASE_DIRECTORY


def main():
    load_dotenv(BASE_DIRECTORY / ".env")
    if os.getenv("APP_ENV", "local") == "production":
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 16 or password.startswith("replace"):
            raise SystemExit("Set a unique DEMO_PASSWORD of at least 16 characters before public deployment.")
        if not os.getenv("GROQ_API_KEY"):
            raise SystemExit("Set GROQ_API_KEY in the server environment.")

    index = BASE_DIRECTORY / "data" / "corpus" / "index_manifest.json"
    if os.getenv("STORAGE_BACKEND") != "cloud" and not index.exists():
        if os.getenv("BOOTSTRAP_ON_START", "false").lower() != "true":
            raise SystemExit("Corpus missing. Run prepare_corpus.py and build_corpus_index.py, or explicitly set BOOTSTRAP_ON_START=true.")
        from prepare_corpus import main as prepare
        from build_corpus_index import main as build
        if not (index.parent / "manifest.json").exists():
            prepare()
        build()

    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1,
                proxy_headers=True, forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"))


if __name__ == "__main__":
    main()
