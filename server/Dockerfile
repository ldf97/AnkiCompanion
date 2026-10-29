FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY . .
ENV ANKI_COMPANION_DATA=/data
EXPOSE 8765
CMD ["python", "-m", "server.main", "--host", "0.0.0.0", "--data", "/data"]
