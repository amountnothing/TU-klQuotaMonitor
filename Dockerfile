FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN mkdir -p /config /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY quota_monitor.py quota_monitor_web.py ./

VOLUME ["/data"]
CMD ["python", "quota_monitor_web.py", "--config", "/config/config.json", "--host", "0.0.0.0", "--port", "8080"]
