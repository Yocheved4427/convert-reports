# ── Stage 1: base image ───────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies: Tesseract (Hebrew), Poppler (pdf2image), shared libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-heb \
        poppler-utils \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Tell Tesseract where to find language data
ENV TESSDATA_PREFIX=/usr/share/tessdata

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY pyproject.toml .
COPY main.py .
COPY src/ src/

# ── Install the package itself (registers the console script) ────────────────
RUN pip install --no-cache-dir .

# ── Runtime directories (overridden by volume mounts) ────────────────────────
RUN mkdir -p input_pdfs output_pdfs

# ── Entry point ───────────────────────────────────────────────────────────────
# Container behaves as a CLI tool:
#   docker run --rm -v $(pwd)/samples:/data attendance-report /data/sample.pdf -o /data/
ENTRYPOINT ["attendance-report"]
CMD ["--help"]
