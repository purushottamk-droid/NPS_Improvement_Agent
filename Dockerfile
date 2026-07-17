# FROM python:3.12-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8080
# CMD ["uvicorn", "api:api", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN echo "=== /app contents ===" && ls -la /app && echo "=== /app/app_auth contents ===" && ls -la /app/app_auth || echo "app_auth NOT FOUND"
EXPOSE 8080
CMD ["uvicorn", "api:api", "--host", "0.0.0.0", "--port", "8080"]