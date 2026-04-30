FROM python:3.12-slim-bookworm
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/config.py backend/constants.py backend/instructions.py backend/main.py \
  backend/verification_signals.py backend/verification_store.py .
COPY backend/policy ./policy
COPY backend/orchestration ./orchestration
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
