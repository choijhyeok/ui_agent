FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/vendor
RUN apt-get update \
  && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/*
COPY apps/agent/ ./

EXPOSE 8123
CMD ["python", "app.py"]
