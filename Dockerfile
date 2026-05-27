FROM python:3.11-slim

RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5009

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5009/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5009", "--worker-tmp-dir", "/tmp", "run:app"]
