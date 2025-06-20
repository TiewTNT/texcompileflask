FROM texlive/texlive:latest-full

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip imagemagick pandoc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

RUN python3 -m ensurepip --upgrade && \
    python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]