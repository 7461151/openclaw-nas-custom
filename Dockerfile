ARG BASE_IMAGE=ghcr.io/openclaw/openclaw:latest
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg \
    gh \
    python3 \
    python3-pip \
    python3-pil \
    openssh-client \
    sshpass \
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
 && python3 -m pip install --no-cache-dir --break-system-packages -U yt-dlp \
 && sed -i 's/^# *zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen zh_CN.UTF-8 \
 && update-locale LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

COPY patch-qqbot-model-label.py /usr/local/bin/patch-qqbot-model-label.py
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh
ENV LC_ALL=zh_CN.UTF-8

COPY lp /usr/local/bin/lp
COPY Epson-L6260_Series-epson-escpr2-en.ppd.gz /usr/share/ppd/Epson/epson-inkjet-printer-escpr/Epson-L6260_Series-epson-escpr2-en.ppd.gz
COPY print-entrypoint.sh /usr/local/bin/print-entrypoint.sh
RUN chmod +x /usr/local/bin/lp /usr/local/bin/print-entrypoint.sh
