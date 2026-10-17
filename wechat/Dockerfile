FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
RUN useradd --uid 10001 --create-home superjlu && mkdir -p /app/.data && chown -R superjlu:superjlu /app
ENV PYTHONUNBUFFERED=1 SUPERJLU_HOST=0.0.0.0 SUPERJLU_PORT=8080 SUPERJLU_DATA_DIR=/app/.data SUPERJLU_ALLOW_DEV_LOGIN=0 SUPERJLU_DIRECT_SCHOOL=1 SUPERJLU_STARTUP_NETWORK_CHECK=0
USER superjlu
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3)"
CMD ["python", "app.py"]
