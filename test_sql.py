import struct
import pyodbc
from azure.identity import DefaultAzureCredential

SQL_SERVER = "atg-agents-server.database.windows.net"
SQL_DATABASE = "atg-agents-db"

credential = DefaultAzureCredential()
token = credential.get_token("https://database.windows.net/.default")

token_bytes = token.token.encode("utf-16-le")
token_struct = struct.pack(
    f"<I{len(token_bytes)}s",
    len(token_bytes),
    token_bytes
)

conn_str = (
    "Driver={ODBC Driver 18 for SQL Server};"
    f"Server=tcp:{SQL_SERVER},1433;"
    f"Database={SQL_DATABASE};"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)

conn = pyodbc.connect(
    conn_str,
    attrs_before={1256: token_struct}
)

print("SQL connection successful!")
print("Database:", conn.cursor().connection.getinfo(pyodbc.SQL_DATABASE_NAME))

conn.close()
