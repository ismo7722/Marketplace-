FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

# Copy only what's needed for the backend
COPY backend/ ./backend/

RUN pip install --no-cache-dir -r backend/requirements.txt

# Install Playwright browsers and OS deps
RUN python -m playwright install --with-deps || true

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:$PORT", "backend.app.main:app"]
