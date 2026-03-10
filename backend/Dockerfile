FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

# Pre-download ML models during build (prevents cold-start on first job)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

COPY . /app

ENV PYTHONUNBUFFERED=1
