FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models

# tesseract for scanned orders; remove if you skip OCR
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# CPU-only torch keeps the image ~2 GB smaller
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
