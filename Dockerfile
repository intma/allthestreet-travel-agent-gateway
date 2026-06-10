# AllTheStreet Agent Gateway — Cloud Run container
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Cloud Run injects PORT (default 8080). Bind to it.
ENV PORT=8080
EXPOSE 8080

# Single worker is fine for I/O-bound async; scale horizontally via Cloud Run.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
