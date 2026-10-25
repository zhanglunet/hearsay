FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEARSAY_HOST=0.0.0.0 \
    HEARSAY_HOME_PORT=8764 \
    HOME=/home/app

RUN useradd --create-home --uid 10001 app
WORKDIR /app/prototype
COPY prototype/ /app/prototype/
RUN chown -R app:app /app

USER app
EXPOSE 8764 8765 8766 8767 8768 8769

CMD ["python", "start_all.py"]
