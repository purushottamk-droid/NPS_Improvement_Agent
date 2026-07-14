FROM python:3.12-slim
WORKDIR /app

# Copy requirements from the current folder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all the python files from the current folder into a package folder
COPY . ./salesforce_mcp_server/

EXPOSE 8080
CMD ["python", "-m", "salesforce_mcp_server.server"]