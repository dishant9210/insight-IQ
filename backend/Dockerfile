# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .
ENV PYTHONPATH=/app
# Expose the port your backend runs on (e.g., 8000)
EXPOSE 8000

# Start the server (adjust if using Gunicorn or another command)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]