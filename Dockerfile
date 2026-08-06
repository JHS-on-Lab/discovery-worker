FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

ARG APP_UID=1001
ARG APP_GID=1001

WORKDIR /app

# 타임존: 서울(KST)
ENV TZ=Asia/Seoul

# undetected-chromedriver(Google News)용 Chrome + Xvfb 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
        xvfb \
        tzdata \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
       http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        google-chrome-stable \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 고정된 UID/GID(1001)를 쓰는 작업용 계정 생성 — 빌드한 사람과 무관하게 항상
# 같은 값이어야 deploy/run.sh 의 --user 값과 어긋나지 않는다.
RUN groupadd --gid "${APP_GID}" appgroup \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --shell /bin/bash \
        appuser \
    && chown -R appuser:appgroup /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appgroup app/ app/
COPY --chown=appuser:appgroup .env .

ENV HOME=/home/appuser

USER appuser