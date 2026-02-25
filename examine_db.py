import sqlite3
conn = sqlite3.connect('scientia.db')
conn.row_factory = sqlite3.Row
print("=== CLASSES ===")
classes = conn.execute('SELECT * FROM classes').fetchall()
for c in classes:
    print(f"ID {c['id']}: {c['class_name']} - {c['section']}")

print("\n=== STUDENTS ===")
students = conn.execute('SELECT s.id, s.name, s.reg_no, c.class_name, c.section FROM students s JOIN classes c ON s.class_id = c.id LIMIT 10').fetchall()
for s in students:
    print(f"ID {s['id']}: {s['name']} ({s['reg_no']}) in {s['class_name']} - {s['section']}")

print("\n=== SUBJECTS ===")
subjects = conn.execute('SELECT s.id, s.subject_name, c.class_name, c.section FROM subjects s JOIN classes c ON s.class_id = c.id LIMIT 10').fetchall()
for sub in subjects:
    print(f"ID {sub['id']}: {sub['subject_name']} for {sub['class_name']} - {sub['section']}")

conn.close()
