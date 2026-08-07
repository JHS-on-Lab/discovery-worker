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

# 이미지를 빌드하는 사람의 UID/GID로 작업용 계정을 만든다(build.sh가
# --build-arg 로 전달). deploy/run.sh 는 --user 를 따로 지정하지 않고 이
# 계정을 그대로 상속해 실행한다 — 배포 계정 하나로 build→run 을 항상
# 순서대로 실행하는 운영 방식이라 빌드 시점과 실행 시점의 UID가 자동으로
# 일치한다.
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