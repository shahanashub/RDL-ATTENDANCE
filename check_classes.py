import sqlite3
conn = sqlite3.connect('scientia.db')
conn.row_factory = sqlite3.Row
classes = conn.execute('SELECT * FROM classes').fetchall()
print('Classes in DB:')
for c in classes:
    print(f"ID: {c['id']}, Name: '{c['class_name']}', Section: '{c['section']}'")
conn.close()
