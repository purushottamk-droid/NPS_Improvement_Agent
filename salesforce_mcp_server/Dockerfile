FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- TEMP DIAGNOSTIC — remove after we find the issue ---
RUN pip show mcp
RUN python -c "import mcp; print('mcp file:', mcp.__file__); from mcp.server.fastmcp import FastMCP; print('fastmcp import OK')"
# ---------------------------------------------------------

COPY . ./salesforce_mcp_server/

EXPOSE 8080
CMD ["python", "-m", "salesforce_mcp_server.server"]