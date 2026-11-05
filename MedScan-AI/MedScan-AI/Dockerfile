# NOTE: written for this project but NOT executed during development (no Docker in the build sandbox).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# CPU-only PyTorch keeps the image small (no CUDA libraries)
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt backend/requirements.txt
RUN grep -v -E "^(torch|torchvision|playwright|pytest|#)" backend/requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY backend backend
COPY frontend frontend
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
