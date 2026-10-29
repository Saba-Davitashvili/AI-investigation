FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/model-cache TOKENIZERS_PARALLELISM=false
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
RUN useradd --uid 10001 --create-home trace && mkdir -p /app/data /app/indexes /app/model-cache && chown -R trace:trace /app
COPY --chown=trace:trace . .
USER trace
EXPOSE 8000
CMD ["python", "serve.py"]
