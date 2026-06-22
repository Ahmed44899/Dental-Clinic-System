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

# Now copy the rest of the project
COPY . .

EXPOSE 8000

CMD ["gunicorn", "dental_clinic.wsgi:application", "--bind", "0.0.0.0:8000"]