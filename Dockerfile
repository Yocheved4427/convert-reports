# ── Stage 1: dependency installer ─────────────────────────────────────────────
# Use a slim builder stage to install Python wheels so the final image stays lean.
FROM python:3.11-slim AS builder

WORKDIR /build

# System build-time deps (needed by some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System runtime dependencies ────────────────────────────────────────────────
# tesseract-ocr       – OCR engine
# tesseract-ocr-heb   – Hebrew language data pack
# poppler-utils       – pdf2image / pdfinfo (PDF → image conversion)
# libglib2.0-0        – GLib shared library (pdfplumber transitive dep)
# libgl1              – OpenGL (required by EasyOCR / OpenCV)
# libgomp1            – OpenMP (used by NumPy / EasyOCR multi-threading)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-heb \
        poppler-utils \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Tell Tesseract where its language data lives
ENV TESSDATA_PREFIX=/usr/share/tessdata

# ── Copy installed Python packages from builder ─────────────────────────────────
COPY --from=builder /install /usr/local

# ── Application source ─────────────────────────────────────────────────────────
WORKDIR /app
COPY pyproject.toml .
COPY main.py .
COPY src/ src/

# Install the package so the ``attendance-report`` console script is registered
RUN pip install --no-cache-dir --no-deps .

# ── Non-root user (security hardening) ────────────────────────────────────────
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# ── Runtime volume mounts (overridden by docker run -v …) ─────────────────────
RUN mkdir -p /home/appuser/input_pdfs /home/appuser/output_pdfs

# ── Entry point ────────────────────────────────────────────────────────────────
# The container behaves as a standalone CLI tool:
#
#   docker run --rm \
#     -v "$(pwd)/samples:/data" \
#     attendance-report \
#     /data/sample.pdf -o /data/
#
ENTRYPOINT ["attendance-report"]
CMD ["--help"]
