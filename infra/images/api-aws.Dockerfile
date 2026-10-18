FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN python -c "import pathlib, ssl, urllib.request; target = pathlib.Path('/etc/rds/us-east-2-bundle.pem'); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(urllib.request.urlopen('https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem', timeout=30).read()); ssl.create_default_context(cafile=str(target))"
COPY app ./app
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8000 8001 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
