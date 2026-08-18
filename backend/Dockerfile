FROM python:3.12-slim

WORKDIR /app

# 1. Installa librerie di sistema per manipolazione immagini
RUN apt-get update && apt-get install -y \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamo i requirements
COPY requirements.txt .

# 2. INSTALLIAMO PYTORCH PER GPU (CUDA 12.1) PRIMA DI SURYA
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Installiamo il resto delle dipendenze (Surya capirà che PyTorch è già installato)
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# Copiamo il resto del codice
COPY . .

# Esponiamo la porta di FastAPI
EXPOSE 8000

# Avviamo il server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]