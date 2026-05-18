FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# Since the WORKDIR is /app, main.py and serviceAccountKey.json will be directly in /app
COPY app/ .

# Expose port 8000 for FastAPI
EXPOSE 8000

# Set timezone (Optional, but useful for Indonesia)
ENV TZ="Asia/Jakarta"

# Run the FastAPI application using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
