FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN addgroup --system blue-me && adduser --system --ingroup blue-me blue-me
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh && mkdir -p /app/uploads && chown -R blue-me:blue-me /app

USER blue-me
EXPOSE 8100
ENTRYPOINT ["./docker-entrypoint.sh"]

