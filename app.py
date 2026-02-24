from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from datetime import date
import hashlib
from functools import wraps
import csv
import io
import os
import sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

# For cross-database compatibility
IntegrityErrors = (sqlite3.IntegrityError,)
if psycopg2:
    IntegrityErrors += (psycopg2.IntegrityError,)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'scientia_secret_2026')  # Use env var in prod

class PostgresWrapper:
    def __init__(self, conn):
        self.conn = conn
    def cursor(self):
        return self.conn.cursor(cursor_factory=RealDictCursor)
    def execute(self, sql, params=None):
        cur = self.cursor()
        if isinstance(sql, str):
            sql = sql.replace('?', '%s')
        cur.execute(sql, params or ())
        return cur
    def commit(self):
        self.conn.commit()
    def close(self):
        self.conn.close()
    def fetchone(self, sql, params=None):
        cur = self.execute(sql, params)
        res = cur.fetchone()
        cur.close()
        return res

class SqliteWrapper:
    def __init__(self, conn):
        self.conn = conn
    def cursor(self):
        return self.conn.cursor()
    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or ())
    def commit(self):
        self.conn.commit()
    def close(self):
        self.conn.close()
    def fetchone(self, sql, params=None):
        cur = self.execute(sql, params)
        res = cur.fetchone()
        return res

def get_db():
    db_url = os.environ.get('DATABASE_URL', 'scientia.db')
    if db_url.startswith('postgres://') or db_url.startswith('postgresql://'):
        # Fix for Render: postgres:// URLs must be postgresql://
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        if psycopg2 is None:
            raise ImportError("psycopg2 is not installed. Please check your requirements.txt")
        conn = psycopg2.connect(db_url)
        return PostgresWrapper(conn)
    else:
        conn = sqlite3.connect(db_url)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return SqliteWrapper(conn)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def init_db():
    """Initialize database with all required tables and sample data"""
    try:
        conn = get_db()
        
        # Determine if we're using Postgres for specific syntax
        is_postgres = isinstance(conn, PostgresWrapper)
        id_type = "SERIAL" if is_postgres else "INTEGER"
        pk_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        
        # Create users table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS users (
            id {pk_type},
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )''')
        
        # Create classes table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS classes (
            id {pk_type},
            class_name TEXT NOT NULL,
            section TEXT NOT NULL,
            UNIQUE(class_name, section)
        )''')
        
        # Create students table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS students (
            id {pk_type},
            reg_no TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            class_id INTEGER,
            user_id INTEGER UNIQUE,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')
        
        # Create subjects table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS subjects (
            id {pk_type},
            class_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            UNIQUE(class_id, subject_name),
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )''')
        
        # Create attendance table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS attendance (
            id {pk_type},
            class_id INTEGER NOT NULL,
            subject_id INTEGER,
            att_date DATE NOT NULL,
            reg_no TEXT NOT NULL,
            present BOOLEAN NOT NULL,
            UNIQUE(class_id, subject_id, att_date, reg_no),
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )''')
        
        # Insert sample data if tables are empty
        user_count = conn.fetchone('SELECT COUNT(*) as count FROM users')['count']
        if user_count == 0:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ('teacher1', hashlib.sha256('pass123'.encode()).hexdigest(), 'teacher'))
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ('admin1', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin'))
        
        class_count = conn.fetchone('SELECT COUNT(*) as count FROM classes')['count']
        if class_count == 0:
            conn.execute("INSERT INTO classes (class_name, section) VALUES (?, ?)", ('Class 10', 'A'))
            conn.execute("INSERT INTO classes (class_name, section) VALUES (?, ?)", ('Class 10', 'B'))
            conn.execute("INSERT INTO classes (class_name, section) VALUES (?, ?)", ('Class 11', 'A'))
        
        student_count = conn.fetchone('SELECT COUNT(*) as count FROM students')['count']
        if student_count == 0:
            conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", ('001', 'Alice', 1))
            conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", ('002', 'Bob', 1))
            conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", ('003', 'Charlie', 2))
            conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", ('004', 'Diana', 3))
        
        conn.commit()
        conn.close()
        print('Database initialized successfully')
    except Exception as e:
        print(f'Database initialization error: {str(e)}')

def is_teacher_or_admin():
    return session.get('role') in ['teacher', 'admin']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.modified = True
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password_input = request.form['password'].strip()
            role = request.form['role'].strip()
            register_no = request.form.get('register_no', '').strip()
            user_class = request.form.get('class', '').strip()
            
            if not username or not password_input:
                flash('Username and password are required', 'danger')
                return redirect(url_for('register'))
            
            password = hashlib.sha256(password_input.encode()).hexdigest()
            
            conn = get_db()
            
            # Insert user
            conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                        (username, password, role))
            conn.commit()
            
            # Get the newly created user
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            
            # If student, create student record
            if role == 'student' and register_no:
                # Parse class format (e.g., "10-A" or "10 A" or just "10")
                class_name = user_class.split('-')[0].split()[0].strip() if user_class else ''
                section = (user_class.split('-')[1] if '-' in user_class else 'A').strip()
                
                if class_name:
                    class_row = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?', 
                                            (f'Class {class_name}', section)).fetchone()
                    
                    if not class_row:
                        conn.execute('INSERT INTO classes (class_name, section) VALUES (?, ?)', 
                                   (f'Class {class_name}', section))
                        conn.commit()
                        class_row = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?', 
                                               (f'Class {class_name}', section)).fetchone()
                    
                    if class_row:
                        # Create student record linked to user
                        conn.execute('INSERT INTO students (reg_no, name, class_id, user_id) VALUES (?, ?, ?, ?)',
                                   (register_no, username, class_row['id'], user['id']))
                        conn.commit()
            
            conn.close()
            
            # Set session variables for automatic login
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.modified = True
            
            flash('Registered successfully! Welcome to Scientia', 'success')
            return redirect(url_for('dashboard'))
            
        except IntegrityErrors as e:
            conn.close()
            error_msg = str(e).lower()
            if 'username' in error_msg:
                flash('Username already exists. Please choose a different username.', 'danger')
            elif 'reg_no' in error_msg:
                flash('Registration number already exists.', 'danger')
            else:
                flash(f'Database error: {str(e)}', 'danger')
            return redirect(url_for('register'))
        except Exception as e:
            if 'conn' in locals():
                conn.close()
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    if not is_teacher_or_admin():
        abort(403)
    conn = get_db()
    if request.method == 'POST':
        class_num = request.form.get('class_num')
        section = request.form.get('section')
        subject_id = request.form.get('subject_id')
        att_date = request.form.get('att_date', date.today().isoformat())
        
        # Find class_id based on class_num and section
        class_id = None
        if class_num and section:
            class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?', 
                                     (f'Class {class_num}', section)).fetchone()
            if class_rec:
                class_id = class_rec['id']
    else:
        class_num = None
        section = None
        subject_id = None
        class_id = None
        att_date = date.today().isoformat()
    
    students = []
    subjects = []
    if class_id:
        students = conn.execute('SELECT * FROM students WHERE class_id = ?', (class_id,)).fetchall()
        subjects = conn.execute('SELECT id, subject_name FROM subjects WHERE class_id = ? ORDER BY subject_name', 
                               (class_id,)).fetchall()
    
    conn.close()
    return render_template('attendance.html', students=students, subjects=subjects,
                          selected_class=class_num, selected_section=section, 
                          selected_subject=subject_id, att_date=att_date, class_id=class_id)

@app.route('/submit_attendance', methods=['POST'])
@login_required
def submit_attendance():
    if not is_teacher_or_admin():
        abort(403)
    
    try:
        conn = get_db()
        
        class_id = request.form.get('class_id')
        subject_id = request.form.get('subject_id')
        att_date = request.form.get('att_date')
        
        if not class_id or not att_date:
            flash('Missing class or date information', 'danger')
            return redirect(url_for('attendance'))
        
        # Subject can be optional - convert to None if empty
        subject_id = subject_id if subject_id else None
        
        # Delete existing attendance records for this date and class (and subject if provided)
        if subject_id:
            conn.execute('DELETE FROM attendance WHERE class_id = ? AND subject_id = ? AND att_date = ?', 
                        (class_id, subject_id, att_date))
        else:
            conn.execute('DELETE FROM attendance WHERE class_id = ? AND subject_id IS NULL AND att_date = ?', 
                        (class_id, att_date))
        
        # Get present students list
        present_regs = request.form.getlist('present[]')
        
        # Get all students in the class
        all_regs = [r['reg_no'] for r in conn.execute('SELECT reg_no FROM students WHERE class_id = ?', (class_id,)).fetchall()]
        
        # Insert attendance records for all students
        for reg in all_regs:
            is_present = reg in present_regs
            conn.execute('INSERT INTO attendance (class_id, subject_id, att_date, reg_no, present) VALUES (?, ?, ?, ?, ?)',
                        (class_id, subject_id, att_date, reg, is_present))
        
        conn.commit()
        conn.close()
        flash('Attendance submitted successfully!', 'success')
        return redirect(url_for('attendance'))
    
    except Exception as e:
        flash(f'Error submitting attendance: {str(e)}', 'danger')
        return redirect(url_for('attendance'))

@app.route('/get_subjects/<class_num>-<section>')
@login_required
def get_subjects(class_num, section):
    """Get all subjects for a class"""
    if not is_teacher_or_admin():
        abort(403)
    
    conn = get_db()
    class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?', 
                            (f'Class {class_num}', section)).fetchone()
    
    if not class_rec:
        conn.close()
        return jsonify([])
    
    subjects = conn.execute('SELECT id, subject_name FROM subjects WHERE class_id = ? ORDER BY subject_name', 
                           (class_rec['id'],)).fetchall()
    conn.close()
    
    return jsonify([dict(s) for s in subjects])

@app.route('/add_subjects', methods=['POST'])
@login_required
def add_subjects():
    """Add subjects for a class"""
    if session.get('role') != 'admin':
        abort(403)
    
    try:
        # Accept either an existing class_id OR class_num + section from the form
        class_id = request.form.get('class_id')
        class_num = request.form.get('class_num')
        section = request.form.get('section')
        subjects_str = request.form.get('subjects', '').strip()

        if not subjects_str or (not class_id and not (class_num and section)):
            flash('Missing class or subjects data', 'danger')
            return redirect(url_for('attendance'))

        conn = get_db()

        # If class_id not provided, find/create class by class_num and section
        if not class_id:
            class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                    (f'Class {class_num}', section)).fetchone()
            if not class_rec:
                conn.execute('INSERT INTO classes (class_name, section) VALUES (?, ?)',
                            (f'Class {class_num}', section))
                conn.commit()
                class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                        (f'Class {class_num}', section)).fetchone()

            if not class_rec:
                conn.close()
                flash('Class not found', 'danger')
                return redirect(url_for('attendance'))

            class_id = class_rec['id']
        else:
            # verify provided class_id exists
            class_rec = conn.execute('SELECT id FROM classes WHERE id = ?', (class_id,)).fetchone()
            if not class_rec:
                conn.close()
                flash('Class not found', 'danger')
                return redirect(url_for('attendance'))

        # Add subjects (split by comma and strip whitespace)
        subjects = [s.strip() for s in subjects_str.split(',') if s.strip()]
        added = 0
        duplicates = 0

        for subject in subjects:
            try:
                conn.execute('INSERT INTO subjects (class_id, subject_name) VALUES (?, ?)',
                            (class_id, subject))
                added += 1
            except IntegrityErrors:
                duplicates += 1

        conn.commit()
        conn.close()

        if added > 0:
            msg = f'Added {added} subject(s)'
            if duplicates > 0:
                msg += f'. ({duplicates} already existed)'
            flash(msg, 'success')
        else:
            flash('No new subjects added', 'warning')

        return redirect(url_for('attendance'))

    except Exception as e:
        flash(f'Error adding subjects: {str(e)}', 'danger')
        return redirect(url_for('attendance'))

@app.route('/submit_student_sheet', methods=['POST'])
@login_required
def submit_student_sheet():
    if session.get('role') != 'admin':
        abort(403)
    
    try:
        sheet_class = request.form.get('sheet_class', '').strip()
        sheet_section = request.form.get('sheet_section', '').strip()
        student_data_str = request.form.get('student_data', '').strip()
        
        if not sheet_class or not sheet_section or not student_data_str:
            flash('Missing required data', 'danger')
            return redirect(url_for('attendance'))
        
        import json
        student_data = json.loads(student_data_str)
        
        if not isinstance(student_data, list) or len(student_data) == 0:
            flash('No student data to submit', 'danger')
            return redirect(url_for('attendance'))
        
        conn = get_db()
        
        # Find or create class
        class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                (f'Class {sheet_class}', sheet_section)).fetchone()
        
        if not class_rec:
            conn.execute('INSERT INTO classes (class_name, section) VALUES (?, ?)',
                        (f'Class {sheet_class}', sheet_section))
            conn.commit()
            class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                    (f'Class {sheet_class}', sheet_section)).fetchone()
        
        class_id = class_rec['id']
        
        # Insert or update students
        added = 0
        updated = 0
        
        for student in student_data:
            reg_no = str(student.get('regNo', '')).strip()
            name = str(student.get('studentName', '')).strip()
            
            if not reg_no or not name:
                continue
            
            existing = conn.execute('SELECT id FROM students WHERE reg_no = ?', (reg_no,)).fetchone()
            
            if existing:
                conn.execute('UPDATE students SET name = ?, class_id = ? WHERE reg_no = ?',
                            (name, class_id, reg_no))
                updated += 1
            else:
                conn.execute('INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)',
                            (reg_no, name, class_id))
                added += 1
        
        conn.commit()
        conn.close()
        
        flash(f'Successfully added {added} new student(s) and updated {updated} student(s)', 'success')
        return redirect(url_for('attendance'))
    
    except json.JSONDecodeError:
        flash('Invalid student data format', 'danger')
        return redirect(url_for('attendance'))
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('attendance'))

@app.route('/upload_students', methods=['POST'])
@login_required
def upload_students():
    if session.get('role') != 'admin':
        abort(403)
    
    try:
        if 'student_file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('attendance'))
        
        file = request.files['student_file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('attendance'))
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect(url_for('attendance'))
        
        # Read and parse CSV
        stream = io.TextIOWrapper(file.stream, encoding='utf8')
        reader = csv.reader(stream)
        
        conn = get_db()
        uploaded_count = 0
        errors = []
        
        for row_num, row in enumerate(reader, 1):
            if len(row) < 4:
                errors.append(f"Row {row_num}: Invalid format (need: Class,Section,Name,RegNo)")
                continue
            
            try:
                class_num = str(row[0]).strip()
                section = str(row[1]).strip().upper()
                name = str(row[2]).strip()
                reg_no = str(row[3]).strip()
                
                if not all([class_num, section, name, reg_no]):
                    errors.append(f"Row {row_num}: Some fields are empty")
                    continue
                
                # Find or create class
                class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                        (f'Class {class_num}', section)).fetchone()
                
                if not class_rec:
                    conn.execute('INSERT INTO classes (class_name, section) VALUES (?, ?)',
                                (f'Class {class_num}', section))
                    conn.commit()
                    class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                            (f'Class {class_num}', section)).fetchone()
                
                class_id = class_rec['id']
                
                # Check if student already exists
                existing = conn.execute('SELECT id FROM students WHERE reg_no = ?', (reg_no,)).fetchone()
                
                if existing:
                    # Update existing student
                    conn.execute('UPDATE students SET name = ?, class_id = ? WHERE reg_no = ?',
                                (name, class_id, reg_no))
                else:
                    # Insert new student
                    conn.execute('INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)',
                                (reg_no, name, class_id))
                
                conn.commit()
                uploaded_count += 1
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        conn.close()
        
        # Flash results
        if uploaded_count > 0:
            flash(f'Successfully uploaded {uploaded_count} student(s)', 'success')
        
        if errors:
            error_msg = ', '.join(errors[:5])
            if len(errors) > 5:
                error_msg += f'... and {len(errors) - 5} more errors'
            flash(f'Uploaded {uploaded_count} students. Errors: {error_msg}', 'warning')
        
        return redirect(url_for('attendance'))
    
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'danger')
        return redirect(url_for('attendance'))

@app.route('/get_attendance_history/<int:class_id>')
@login_required
def get_attendance_history(class_id):
    if not is_teacher_or_admin():
        abort(403)
    
    subject_id = request.args.get('subject_id', None)
    
    conn = get_db()
    
    if subject_id:
        history = conn.execute('SELECT DISTINCT att_date FROM attendance WHERE class_id = ? AND subject_id = ? ORDER BY att_date DESC', 
                              (class_id, subject_id)).fetchall()
    else:
        history = conn.execute('SELECT DISTINCT att_date FROM attendance WHERE class_id = ? AND subject_id IS NULL ORDER BY att_date DESC', 
                              (class_id,)).fetchall()
    
    records = []
    class_info = conn.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    
    if not class_info:
        conn.close()
        return jsonify({'success': False, 'message': 'Class not found'})
    
    for d in history:
        att_date = d['att_date']
        students_att = conn.execute('''
            SELECT s.reg_no, s.name, a.present FROM students s
            LEFT JOIN attendance a ON s.reg_no = a.reg_no AND a.att_date = ? AND a.class_id = ? AND a.subject_id = ?
            WHERE s.class_id = ?
        ''', (att_date, class_id, subject_id, class_id)).fetchall()
        
        records.append({
            'date': att_date,
            'class_name': class_info['class_name'],
            'section': class_info['section'],
            'students': [dict(student) for student in students_att]
        })
    
    conn.close()
    return jsonify({'success': True, 'records': records})

@app.route('/history')
@login_required
def history():
    if not is_teacher_or_admin():
        abort(403)
    conn = get_db()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    conn.close()
    return render_template('history.html', classes=classes)

@app.route('/attendance_history/<int:class_id>')
@login_required
def attendance_history(class_id):
    if not is_teacher_or_admin():
        abort(403)
    
    subject_id = request.args.get('subject_id', None)
    
    conn = get_db()
    
    if subject_id:
        history = conn.execute('SELECT DISTINCT att_date FROM attendance WHERE class_id = ? AND subject_id = ? ORDER BY att_date DESC', 
                              (class_id, subject_id)).fetchall()
    else:
        history = conn.execute('SELECT DISTINCT att_date FROM attendance WHERE class_id = ? AND subject_id IS NULL ORDER BY att_date DESC', 
                              (class_id,)).fetchall()
    
    records = []
    class_info = conn.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    
    for d in history:
        att_date = d['att_date']
        students_att = conn.execute('''
            SELECT s.reg_no, s.name, a.present FROM students s
            LEFT JOIN attendance a ON s.reg_no = a.reg_no AND a.att_date = ? AND a.class_id = ? AND a.subject_id = ?
            WHERE s.class_id = ?
        ''', (att_date, class_id, subject_id, class_id)).fetchall()
        
        records.append({'date': att_date, 'class': class_info, 'students': students_att})
    
    # Get subjects for this class
    subjects = conn.execute('SELECT id, subject_name FROM subjects WHERE class_id = ? ORDER BY subject_name',
                           (class_id,)).fetchall()
    
    conn.close()
    return render_template('history.html', records=records, class_id=class_id, 
                          selected_subject=subject_id, subjects=subjects)

# Initialize database on startup
init_db()

if __name__ == '__main__':
    app.run(debug=True)
