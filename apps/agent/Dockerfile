FROM python:3.12-alpine

WORKDIR /app
COPY apps/agent/pyproject.toml ./pyproject.toml
COPY apps/agent/app.py ./app.py

EXPOSE 8123
CMD ["python", "app.py"]
