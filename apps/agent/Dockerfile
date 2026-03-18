FROM python:3.12-slim

WORKDIR /app
ENV PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org pypi.python.org"
COPY apps/agent/app.py ./app.py
COPY apps/agent/local_figma_agent ./local_figma_agent

RUN pip install --no-cache-dir \
    'fastapi>=0.115.12,<1.0.0' \
    'langgraph>=0.6.0,<1.0.0' \
    'openai>=1.75.0,<2.0.0' \
    'psycopg[binary]>=3.2.6,<4.0.0' \
    'uvicorn>=0.34.0,<1.0.0'

EXPOSE 8123
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8123"]
