# ── Stage 1: base image ───────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies required by pdfplumber, EasyOCR and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
# Copy only requirements first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY main.py .
COPY src/ src/

# ── Runtime directories (can be overridden with volume mounts) ────────────────
RUN mkdir -p input_pdfs output_pdfs

# ── Default command ───────────────────────────────────────────────────────────
# Mount input_pdfs/ and output_pdfs/ as volumes when running:
#   docker run --rm \
#     -v "$(pwd)/input_pdfs:/app/input_pdfs" \
#     -v "$(pwd)/output_pdfs:/app/output_pdfs" \
#     convert-reports
ENTRYPOINT ["python", "main.py"]
CMD ["--input", "input_pdfs/", "--output", "output_pdfs/"]
