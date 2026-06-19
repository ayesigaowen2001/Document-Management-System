# Step 1: Use the official lightweight Python 3.14 image
FROM python:3.14-slim

# Step 2: Set environment variables to optimize Python for Docker
# Prevents Python from writing .pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
# Forces stdout and stderr streams to be unbuffered (real-time logs)
ENV PYTHONUNBUFFERED=1

# Step 3: Set the working directory inside the container
WORKDIR /app

# Step 4: Install system dependencies required for compilation (e.g., database drivers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Step 5: Copy requirements first to leverage Docker's caching mechanism
COPY requirements.txt /app/

# Step 6: Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Step 7: Copy the rest of your local Django project source code into the container
COPY . /app/

# Step 8: Inform Docker that the container listens on port 8000 at runtime
EXPOSE 8000

# Step 9: Run migrations, collect static files, and start Gunicorn
CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:8000 DMS.wsgi:application"]
