# Dockerfile
# 使用官方的 Python 基礎映像
FROM python:3.9-slim-buster

# 設置工作目錄
WORKDIR /app

# 安裝 Chrome 瀏覽器和必要的依賴
# 這些依賴對於無頭 Chrome 運行是必需的
RUN apt-get update && apt-get install -y \
    gnupg \
    wget \
    curl \
    unzip \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libglib2.0-bin \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    # 針對一些低內存環境可能需要
    xvfb \
    # 清理 apt 快取以減少映像大小
    && rm -rf /var/lib/apt/lists/*

# 下載並安裝 Google Chrome
# IMPORTANT: 請檢查 https://googlechromelabs.github.io/chrome-for-testing/ 以獲取最新版本
# 確保 CHROME_VERSION 和 CHROMEDRIVER_VERSION 匹配
ENV CHROME_VERSION=126.0.6478.182
ENV CHROMEDRIVER_VERSION=126.0.6478.182

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# 下載並安裝 ChromeDriver
RUN CHROMEDRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
    grep -oP "\"${CHROMEDRIVER_VERSION}\": {\"chromedriver\": \\[\\{\"platform\": \"linux64\", \"url\": \"\\K[^\"]+") \
    && wget -q "${CHROMEDRIVER_URL}" -O chromedriver.zip \
    && unzip chromedriver.zip \
    && mv chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && rm -rf chromedriver.zip chromedriver-linux64 \
    && chmod +x /usr/bin/chromedriver

# 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式程式碼
COPY . .

# Cloud Run 服務預期監聽 PORT 環境變數
ENV PORT 8080

# 啟動應用程式 (使用 Gunicorn 作為 WSGI 服務器，推薦用於生產環境)
# Gunicorn 會自動尋找 app.py 中的 'app' 實例
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]