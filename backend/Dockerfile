FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

COPY . .

ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
RUN python -m playwright install --with-deps || true

RUN mkdir -p /app/data

EXPOSE 8000
ENV PORT=8000

CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 --timeout 600 -b 0.0.0.0:${PORT:-8000} app.main:app"]
