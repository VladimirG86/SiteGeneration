FROM python:3.11-slim
WORKDIR /app
COPY sitegen/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sitegen/ .
ENV SITEGEN_DATA_DIR=/data PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
