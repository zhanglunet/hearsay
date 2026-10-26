FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEARSAY_HOST=0.0.0.0 \
    HEARSAY_HOME_PORT=8764 \
    HOME=/home/app

RUN useradd --create-home --uid 10001 app
WORKDIR /app/prototype
COPY prototype/ /app/prototype/
# M4 进度页按 Markdown 表格解析 can-do 清单（m4_plan/can_do.py 的 DEFAULT_LIST）
COPY docs/design/cefr-can-do-listening-speaking.md /app/docs/design/
RUN chown -R app:app /app

USER app
EXPOSE 8764

CMD ["python", "start_all.py"]
