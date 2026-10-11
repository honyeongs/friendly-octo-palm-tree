FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-runtime.lock .
RUN pip install --no-cache-dir -r requirements-runtime.lock
COPY pyproject.toml README.md THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY third_party ./third_party
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home netsec
USER 10001
EXPOSE 8890
CMD ["netsec", "monitor", "--host", "0.0.0.0", "--port", "8890"]
