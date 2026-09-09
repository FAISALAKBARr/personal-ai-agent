FROM python:3.11-slim

# Without this, print() output (our provider observability logs included)
# can sit in a buffer and show up late or out of order in `docker compose
# logs` — Python only auto-flushes on every line when stdout is a real
# terminal, which it isn't inside a container.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
