FROM python:3.12-slim
WORKDIR /app
COPY salesforce_mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY salesforce_mcp_server/ ./salesforce_mcp_server/
EXPOSE 8080
CMD ["python", "-m", "salesforce_mcp_server.server"]
