FROM mcr.microsoft.com/playwright/python:latest

# Place the backend at /app/backend and run from there so `import app` resolves
WORKDIR /app/backend

# Copy backend sources into container working dir
COPY backend/ .

# Install Python deps
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Playwright browsers install into the project's `playwright-browsers` folder
ENV PLAYWRIGHT_BROWSERS_PATH=/app/backend/playwright-browsers
# Install Playwright browsers and OS deps
RUN python -m playwright install --with-deps || true

EXPOSE 8000
ENV PORT=8000

# Use shell form so $PORT expands at runtime; run module as `app.main:app` so
# inside the container `import app` works (package is at /app/backend/app).
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} app.main:app"]
