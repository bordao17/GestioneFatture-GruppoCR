FROM python:3.12-slim

WORKDIR /app

# Installiamo prima i requirements per sfruttare la cache di Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamo il resto del codice
COPY . .

# Esponiamo la porta di FastAPI
EXPOSE 8000

# Avviamo il server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
