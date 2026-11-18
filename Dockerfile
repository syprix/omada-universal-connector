FROM python:3.13-alpine

WORKDIR /app
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/doc/omada-universal-connector/
COPY app/ /app/app/
COPY tools/wifi_diagnose.py /app/tools/wifi_diagnose.py
COPY tools/controller_probe.py /app/tools/controller_probe.py

RUN addgroup -S connector && adduser -S -G connector -u 10001 connector \
    && mkdir -p /state/change-journal \
    && chown 10001:10001 /state/change-journal \
    && chmod 0700 /state/change-journal
USER 10001:10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8080 \
    OMADA_BASE_URL=https://192.0.2.1 \
    OMADA_TIMEOUT_SECONDS=5

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
ENTRYPOINT ["python", "/app/app/main.py"]
