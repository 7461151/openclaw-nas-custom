ARG BASE_IMAGE=ghcr.io/openclaw/openclaw:latest
ARG GEMINI_CLI_VERSION=0.38.0
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg \
    python3 \
    python3-pil \
    locales \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fonts-liberation2 \
    cups \
    cups-client \
    cups-bsd \
    cups-filters \
    printer-driver-escpr \
    pandoc \
    wkhtmltopdf \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
 && npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION} \
 && gemini --version \
 && sed -i 's/^# *zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen zh_CN.UTF-8 \
 && update-locale LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

COPY patch-qqbot-heartbeat.py /tmp/patch-qqbot-heartbeat.py
COPY patch-qqbot-model-label.py /usr/local/bin/patch-qqbot-model-label.py
RUN python3 /tmp/patch-qqbot-heartbeat.py && rm -f /tmp/patch-qqbot-heartbeat.py
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh
ENV LC_ALL=zh_CN.UTF-8

COPY lp /usr/local/bin/lp
COPY Epson-L6260_Series-epson-escpr2-en.ppd.gz /usr/share/ppd/Epson/epson-inkjet-printer-escpr/Epson-L6260_Series-epson-escpr2-en.ppd.gz
COPY print-entrypoint.sh /usr/local/bin/print-entrypoint.sh
RUN chmod +x /usr/local/bin/lp /usr/local/bin/print-entrypoint.sh
