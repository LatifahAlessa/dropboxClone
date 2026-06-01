FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY dropboxClone/requirements.txt .
RUN pip install -r requirements.txt

COPY dropboxClone/ .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]