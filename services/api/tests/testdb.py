import psycopg

conn = psycopg.connect(
    "host=127.0.0.1 port=55432 dbname=opme user=opme password=opme_dev_secret"
)
print("conectou com psycopg")
conn.close()