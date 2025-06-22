FROM python:3.11.12-slim-bookworm

# install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    # VNC and noVNC components
    x11vnc xvfb fluxbox novnc websockify \
    # Other dependencies
    libnss3 libxss1 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libxcomposite1 libxrandr2 libgbm1 libasound2 \
    fonts-liberation \
    curl \
    unzip \
    xauth \
    x11-utils \
  && rm -rf /var/lib/apt/lists/*

# install google chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get -y update
RUN apt-get install -y --no-install-recommends google-chrome-stable && rm -rf /var/lib/apt/lists/*

# set the working directory to /src
WORKDIR /src

# upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# install dependencies
RUN python -m pip install --no-cache-dir -r requirements.txt

# copy the current directory contents into the image
COPY . /src

# set display port to avoid crash
ENV DISPLAY=:1
ENV PYTHONUNBUFFERED=1

RUN python3 -c "from undetected_chromedriver.patcher import Patcher; p = Patcher(); p.auto()"

# Create a startup script that launches all services
RUN echo '#!/bin/bash' > /src/start.sh && \
    echo 'export DISPLAY=:1' >> /src/start.sh && \
    echo 'Xvfb $DISPLAY -screen 0 1920x1080x24+32 -ac &' >> /src/start.sh && \
    echo '# Wait for Xvfb to be ready by checking for the socket file' >> /src/start.sh && \
    echo 'while [ ! -S /tmp/.X11-unix/X${DISPLAY:1} ]; do echo "Waiting for Xvfb socket..."; sleep 1; done' >> /src/start.sh && \
    echo 'fluxbox &' >> /src/start.sh && \
    echo 'x11vnc -display $DISPLAY -forever -nopw -create &' >> /src/start.sh && \
    echo 'websockify -D --web /usr/share/novnc/ 6901 localhost:5900 &' >> /src/start.sh && \
    echo '# All services launched, now starting the main application' >> /src/start.sh && \
    echo 'exec python api.py' >> /src/start.sh && \
    chmod +x /src/start.sh

# Use the startup script as the entrypoint
ENTRYPOINT ["/src/start.sh"]

# Set DNS servers to resolve Supabase
RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf
