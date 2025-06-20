# Base image with LaTeX circus already installed
FROM texlive/texlive:latest-full

# ---- 1. System packages ----------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-venv imagemagick pandoc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- 2. Python virtual environment (PEP 668 force-field) -------------------
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"      # makes `python`, `pip`, etc. point to venv

# ---- 3. Upgrade core Python tooling (inside venv, so nobody cries) ----------
RUN pip install --upgrade pip setuptools wheel

# ---- 4. App setup ----------------------------------------------------------
WORKDIR /app

# → dependency layer first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# → bring in the rest of the source
COPY . .

# ---- 5. Gunicorn party -----------------------------------------------------
EXPOSE 8000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
