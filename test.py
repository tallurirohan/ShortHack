import sqlite3

conn = sqlite3.connect('SAMdashboard.db')
cursor = conn.cursor()
cursor.execute("SELECT email, password FROM users")
rows = cursor.fetchall()
conn.close()

for email, pw in rows:
    print(email, pw)