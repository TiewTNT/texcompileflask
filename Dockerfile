FROM texlive/texlive:latest-full

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-venv imagemagick pandoc gnuplot pygments ghostscript \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel

WORKDIR /app
ENV PORT=8000

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn -w 4 -b 0.0.0.0:$PORT wsgi:app
