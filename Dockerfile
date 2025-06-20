FROM python:3.11.12-slim-bookworm

# install required packages
RUN apt-get update && apt-get install -y \
    wget gnupg \
    python3-tk python3-dev xvfb \
    libnss3 libxss1 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libxcomposite1 libxrandr2 libgbm1 libasound2 \
    fonts-liberation \
  && rm -rf /var/lib/apt/lists/*

# install google chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get -y update
RUN apt-get install -y google-chrome-stable && rm -rf /var/lib/apt/lists/*

# set the working directory to /src
WORKDIR /src

# upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip

# install dependencies
RUN python -m pip install --no-cache-dir \
    customtkinter==5.2.1 \
    openpyxl==3.1.2 \
    PyAutoGUI==0.9.53 \
    python-telegram-bot==20.6 \
    selenium==4.32.0 \
    seleniumbase==4.38.0 \
    undetected-chromedriver==3.5.5 \
    requests==2.32.3 \
    python-dotenv==1.0.0 \
    Flask==2.2.2 \
    Werkzeug==2.2.2

# copy the current directory contents into the image
COPY . /src

# set display port to avoid crash
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

RUN python3 - <<EOF
from undetected_chromedriver.patcher import Patcher
p = Patcher()
p.auto()
EOF

# Create a startup script that starts Xvfb and then the API
RUN echo '#!/bin/sh' > /src/start.sh && \
    echo 'Xvfb :99 -screen 0 1920x1080x16 -ac +extension GLX +render -noreset &' >> /src/start.sh && \
    echo 'exec python api.py' >> /src/start.sh && \
    chmod +x /src/start.sh

# Use the startup script as the entrypoint
ENTRYPOINT ["/src/start.sh"]

# Set DNS servers to resolve Supabase
RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf
