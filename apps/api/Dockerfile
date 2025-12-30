FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy only the API folder so main.py ends up at /app/main.py
COPY apps/api/ /app/

ENV XRAY_DB=/data/xray.db
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
