FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffering output — cleaner logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for psycopg2 and pillow
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first — this is a caching trick
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create an unprivileged account for the Django process.
RUN addgroup --system app && adduser --system --ingroup app app

# Copy application files.
COPY . .

# Prepare directories that may need application-level access.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media

# Everything below runs without root privileges.
USER app

# Bake static assets into the immutable production image.
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["./entrypoint.sh"]