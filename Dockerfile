# --- build stage: install Python deps into an isolated venv ---
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- runtime stage: slim image with only what the app needs to run ---
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# System libraries required at runtime for OCR (tesseract), .doc extraction
# (antiword), image handling (libgl1) and MIME sniffing (libmagic1).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    antiword \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Run as an unprivileged user instead of root.
RUN useradd --create-home --uid 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Liveness probe against the app's own health endpoint (uses stdlib, no curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
