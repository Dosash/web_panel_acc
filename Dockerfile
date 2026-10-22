# Python именно 3.12: opentele тянет PyQt5, который на 3.13+ ставится ненадёжно
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# QtCore из PyQt5 (opentele читает им tdata) нужна glib
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# зависимости отдельным слоем — пересобираются только при смене requirements.txt;
# gcc нужен только для сборки tgcrypto и удаляется в том же слое
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc libc6-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY static ./static

# база, ключ шифрования сессий и кэш — в томе ./data
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % (os.getenv('WEB_PORT') or os.getenv('PORT') or '8080'), timeout=4)" || exit 1

CMD ["python", "-m", "app"]
