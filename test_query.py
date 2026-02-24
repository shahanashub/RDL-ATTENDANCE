import sqlite3
conn=sqlite3.connect('scientia.db')
cur=conn.cursor()
cur.execute("SELECT c.class_name, c.section, s.subject_name FROM subjects s JOIN classes c ON s.class_id=c.id WHERE c.class_name=? AND c.section=?",('Class 1','A'))
rows=cur.fetchall()
print('Subjects for Class 1-A:')
for r in rows:
    print(' -', r[2])
conn.close()
