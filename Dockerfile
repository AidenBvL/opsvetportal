FROM python:3.13-slim

# Tesseract (met Nederlands taalpakket) voor OCR van gescande documenten.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-nld tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Verzamel de statische bestanden met dezelfde (productie)instellingen als de live server,
# anders ontbreekt het manifest van whitenoise. De sleutel hier is alleen voor het bouwen.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-not-secret python manage.py collectstatic --noinput

ENV DJANGO_DEBUG=0
EXPOSE 8000
CMD ["sh", "start.sh"]
