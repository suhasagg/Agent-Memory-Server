FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
