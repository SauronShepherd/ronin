FROM python:3.11-slim

LABEL org.opencontainers.image.title="Ronin"
LABEL org.opencontainers.image.description="Ronin prerelease bootstrap container"
LABEL org.opencontainers.image.source="https://github.com/SauronShepherd/ronin"
LABEL org.opencontainers.image.licenses="Apache-2.0"

RUN useradd --create-home --uid 65532 ronin
WORKDIR /app
COPY docker/bootstrap_server.py /app/bootstrap_server.py
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read()" || exit 1
CMD ["python", "/app/bootstrap_server.py"]
