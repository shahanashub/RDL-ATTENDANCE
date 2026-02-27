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
except ImportError as e:
    psycopg2 = None
    print(f"Warning: psycopg2 import failed: {e}")

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
            mother_name TEXT,
            mother_phone TEXT,
            father_name TEXT,
            father_phone TEXT,
            address TEXT,
            dob TEXT,
            blood_group TEXT,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')

        # Simple migration for existing tables
        new_student_cols = [
            ('mother_name', 'TEXT'), ('mother_phone', 'TEXT'),
            ('father_name', 'TEXT'), ('father_phone', 'TEXT'),
            ('address', 'TEXT'), ('dob', 'TEXT'), ('blood_group', 'TEXT')
        ]
        
        for col_name, col_type in new_student_cols:
            try:
                # Postgres supports ADD COLUMN IF NOT EXISTS in 9.6+
                if isinstance(conn, PostgresWrapper):
                    conn.execute(f"ALTER TABLE students ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                else:
                    conn.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}")
            except Exception:
                # For SQLite or older Postgres, catch if column already exists
                if isinstance(conn, PostgresWrapper):
                    conn.conn.rollback() # Reset transaction state if failed
                pass
        
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

        # Create teacher_profiles table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS teacher_profiles (
            id {pk_type},
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            register_id TEXT UNIQUE NOT NULL,
            main_subject TEXT,
            class_advisor TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')

        # Create admin_profiles table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS admin_profiles (
            id {pk_type},
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            register_id TEXT UNIQUE NOT NULL,
            main_subject TEXT,
            class_advisor TEXT,
            role_title TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')

        # Create timetables table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS timetables (
            id {pk_type},
            class_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            faculty_name TEXT NOT NULL,
            UNIQUE(class_id, day, subject_name),
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )''')

        # Create exams table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS exams (
            id {pk_type},
            exam_name TEXT NOT NULL,
            UNIQUE(exam_name)
        )''')

        # Create marks table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS marks (
            id {pk_type},
            class_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            reg_no TEXT NOT NULL,
            marks_scored REAL NOT NULL,
            total_marks REAL NOT NULL,
            pass_mark REAL NOT NULL,
            UNIQUE(class_id, subject_id, exam_id, reg_no),
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')

        # Create fees table
        conn.execute(f'''CREATE TABLE IF NOT EXISTS fees (
            id {pk_type},
            student_name TEXT NOT NULL,
            reg_no TEXT NOT NULL,
            month TEXT NOT NULL,
            payment_date DATE NOT NULL,
            payment_mode TEXT NOT NULL,
            balance_amount REAL NOT NULL,
            class_id INTEGER NOT NULL,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )''')
        
        # Insert sample data if tables are empty
        user_count_res = conn.fetchone('SELECT COUNT(*) as count FROM users')
        user_count = user_count_res['count'] if user_count_res else 0
        if user_count == 0:
            print("Inserting sample users...", flush=True)
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ('teacher1', hashlib.sha256('pass123'.encode()).hexdigest(), 'teacher'))
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ('admin1', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin'))
            conn.commit()
        
        # Insert more comprehensive sample data if empty
        class_count_res = conn.fetchone('SELECT COUNT(*) as count FROM classes')
        class_count = class_count_res['count'] if class_count_res else 0
        if class_count == 0:
            print("Inserting sample classes...", flush=True)
            for i in range(1, 13):
                conn.execute("INSERT INTO classes (class_name, section) VALUES (?, ?)", (f'Class {i}', 'A'))
                conn.execute("INSERT INTO classes (class_name, section) VALUES (?, ?)", (f'Class {i}', 'B'))
            conn.commit()
        
        student_count_res = conn.fetchone('SELECT COUNT(*) as count FROM students')
        student_count = student_count_res['count'] if student_count_res else 0
        if student_count == 0:
            print("Inserting sample students...", flush=True)
            # Add at least 2 students to every class 'A' for testing
            classes = conn.execute("SELECT id, class_name FROM classes WHERE section = 'A'").fetchall()
            for cls in classes:
                name1 = f"Student A ({cls['class_name']})"
                name2 = f"Student B ({cls['class_name']})"
                conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", 
                           (f"REG-{cls['id']}-1", name1, cls['id']))
                conn.execute("INSERT INTO students (reg_no, name, class_id) VALUES (?, ?, ?)", 
                           (f"REG-{cls['id']}-2", name2, cls['id']))
            conn.commit()
        
        conn.close()
        print('OK Database initialized successfully', flush=True)
    except Exception as e:
        print(f'ERROR Database initialization error: {str(e)}', flush=True)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

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
        role = request.form.get('role')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ? AND role = ?', 
                           (username, password, role)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.modified = True
            return redirect(url_for('dashboard'))
        flash(f'Invalid credentials or incorrect role selected for {username}')
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
    # Removed is_teacher_or_admin restriction to allow students to view subject lists
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

@app.route('/get_class_students/<int:class_id>')
@login_required
def get_class_students(class_id):
    """Get all students in a specific class"""
    if not is_teacher_or_admin():
        abort(403)
    
    conn = get_db()
    students = conn.execute('SELECT reg_no, name FROM students WHERE class_id = ? ORDER BY name', (class_id,)).fetchall()
    conn.close()
    
    return jsonify({'success': True, 'students': [dict(s) for s in students]})

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
                conn.commit()
                added += 1
            except IntegrityErrors:
                # For Postgres, we must rollback the failed transaction before continuing
                if hasattr(conn.conn, 'rollback'):
                    conn.conn.rollback()
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
    # Removed is_teacher_or_admin restriction to allow students to view their history
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
        
        # Correctly handle NULL subject_id in the LEFT JOIN for both SQLite and Postgres
        if subject_id:
            subj_clause = "a.subject_id = ?"
            subj_params = (att_date, class_id, subject_id, class_id)
        else:
            subj_clause = "a.subject_id IS NULL"
            subj_params = (att_date, class_id, class_id)
            
        students_att = conn.execute(f'''
            SELECT s.reg_no, s.name, a.present, a.id as att_id FROM students s
            LEFT JOIN attendance a ON s.reg_no = a.reg_no AND a.att_date = ? AND a.class_id = ? AND {subj_clause}
            WHERE s.class_id = ?
        ''', subj_params).fetchall()
        
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
    # Removed is_teacher_or_admin restriction to allow students to access the page
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
        
        # Correctly handle NULL subject_id in the LEFT JOIN
        if subject_id:
            subj_clause = "a.subject_id = ?"
            subj_params = (att_date, class_id, subject_id, class_id)
        else:
            subj_clause = "a.subject_id IS NULL"
            subj_params = (att_date, class_id, class_id)
            
        students_att = conn.execute(f'''
            SELECT s.reg_no, s.name, a.present, a.id as att_id FROM students s
            LEFT JOIN attendance a ON s.reg_no = a.reg_no AND a.att_date = ? AND a.class_id = ? AND {subj_clause}
            WHERE s.class_id = ?
        ''', subj_params).fetchall()
        
        records.append({'date': att_date, 'class': class_info, 'students': students_att})
    
    # Get subjects for this class
    subjects = conn.execute('SELECT id, subject_name FROM subjects WHERE class_id = ? ORDER BY subject_name',
                           (class_id,)).fetchall()
    
    conn.close()
    return render_template('history.html', records=records, class_id=class_id, 
                          selected_subject=subject_id, subjects=subjects)

@app.route('/education')
@login_required
def education():
    return render_template('education.html')

@app.route('/exam_marks', methods=['GET', 'POST'])
@login_required
def exam_marks():
    conn = get_db()
    exams = conn.execute('SELECT * FROM exams ORDER BY exam_name').fetchall()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    print(f"DEBUG: Found {len(classes)} classes")
    
    if request.method == 'POST' and session.get('role') in ['admin', 'teacher']:
        # Uploading marks logic handled in separate route for simplicity or here
        pass

    conn.close()
    return render_template('exam_marks.html', exams=exams, classes=classes)

@app.route('/upload_marks', methods=['POST'])
@login_required
def upload_marks():
    if session.get('role') not in ['admin', 'teacher']:
        abort(403)
    
    try:
        class_id = request.form.get('class_id')
        subject_name = request.form.get('subject_name')
        exam_name = request.form.get('exam_name')
        total_mark = float(request.form.get('total_mark'))
        pass_mark = float(request.form.get('pass_mark'))
        
        conn = get_db()
        
        # Get or create subject
        subject = conn.execute('SELECT id FROM subjects WHERE class_id = ? AND LOWER(subject_name) = LOWER(?)', 
                             (class_id, subject_name.strip())).fetchone()
        if not subject:
            conn.execute('INSERT INTO subjects (class_id, subject_name) VALUES (?, ?)', 
                         (class_id, subject_name.strip()))
            conn.commit()
            subject = conn.execute('SELECT id FROM subjects WHERE class_id = ? AND LOWER(subject_name) = LOWER(?)', 
                                 (class_id, subject_name.strip())).fetchone()
        subject_id = subject['id']

        # Get or create exam
        exam = conn.execute('SELECT id FROM exams WHERE LOWER(exam_name) = LOWER(?)', (exam_name.strip(),)).fetchone()
        if not exam:
            conn.execute('INSERT INTO exams (exam_name) VALUES (?)', (exam_name.strip(),))
            conn.commit()
            exam = conn.execute('SELECT id FROM exams WHERE LOWER(exam_name) = LOWER(?)', (exam_name.strip(),)).fetchone()
        
        exam_id = exam['id']
        
        # Process marks for each student
        student_marks = request.form.getlist('marks[]')
        student_regs = request.form.getlist('reg_nos[]')
        
        for reg_no, marks in zip(student_regs, student_marks):
            if marks.strip():
                # Delete existing if any
                conn.execute('DELETE FROM marks WHERE class_id = ? AND subject_id = ? AND exam_id = ? AND reg_no = ?',
                           (class_id, subject_id, exam_id, reg_no))
                conn.execute('''INSERT INTO marks (class_id, subject_id, exam_id, reg_no, marks_scored, total_marks, pass_mark)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                           (class_id, subject_id, exam_id, reg_no, float(marks), total_mark, pass_mark))
        
        conn.commit()
        conn.close()
        flash('Exam marks uploaded successfully!', 'success')
        return redirect(url_for('exam_marks'))
    except Exception as e:
        flash(f'Error uploading marks: {str(e)}', 'danger')
        return redirect(url_for('exam_marks'))

@app.route('/get_exam_results')
@login_required
def get_exam_results():
    class_id = request.args.get('class_id')
    exam_id = request.args.get('exam_id')
    reg_no = request.args.get('reg_no') # if student is viewing their own
    
    if not exam_id:
        return jsonify({'success': False, 'message': 'Exam ID is required'})

    conn = get_db()
    
    # Students view merged marks for all subjects in an exam
    if session.get('role') == 'student' or reg_no:
        # If student and no reg_no provided, try to find it from user_id
        if not reg_no and session.get('role') == 'student':
            student = conn.execute('SELECT reg_no FROM students WHERE user_id = ?', (session['user_id'],)).fetchone()
            reg_no = student['reg_no'] if student else None
            
        if not reg_no:
            conn.close()
            return jsonify({'success': False, 'message': 'Registration number not found'})
            
        query = '''
            SELECT s.subject_name, m.marks_scored, m.total_marks, m.pass_mark, 
            std.name as student_name, std.reg_no
            FROM marks m
            JOIN subjects s ON m.subject_id = s.id
            JOIN students std ON m.reg_no = std.reg_no
            WHERE m.exam_id = ? AND m.reg_no = ?
        '''
        results = conn.execute(query, (exam_id, reg_no)).fetchall()
    else:
        # Admins/Teachers view all marks for a class and exam
        try:
            if not class_id or class_id == 'undefined':
                conn.close()
                return jsonify({'success': False, 'message': 'Class selection is invalid'})
            class_id = int(class_id)
        except (ValueError, TypeError):
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid Class ID'})
            
        query = '''
            SELECT std.name as student_name, std.reg_no, s.subject_name, m.marks_scored, m.total_marks, m.pass_mark, m.id
            FROM marks m
            JOIN subjects s ON m.subject_id = s.id
            JOIN students std ON m.reg_no = std.reg_no
            WHERE m.exam_id = ? AND m.class_id = ?
            ORDER BY std.reg_no, s.subject_name
        '''
        results = conn.execute(query, (exam_id, class_id)).fetchall()
        
    conn.close()
    return jsonify({'success': True, 'results': [dict(r) for r in results]})

@app.route('/fees', methods=['GET', 'POST'])
@login_required
def fees():
    conn = get_db()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    conn.close()
    return render_template('fees.html', classes=classes)

@app.route('/upload_fee_receipt', methods=['POST'])
@login_required
def upload_fee_receipt():
    if session.get('role') != 'admin':
        abort(403)
        
    try:
        student_name = request.form.get('student_name')
        reg_no = request.form.get('reg_no')
        month = request.form.get('month')
        date = request.form.get('date')
        mode = request.form.get('mode')
        balance = float(request.form.get('balance'))
        class_id = request.form.get('class_id')
        
        conn = get_db()
        conn.execute('''INSERT INTO fees (student_name, reg_no, month, payment_date, payment_mode, balance_amount, class_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (student_name, reg_no, month, date, mode, balance, class_id))
        conn.commit()
        conn.close()
        flash('Fee receipt saved successfully!', 'success')
        return redirect(url_for('fees'))
    except Exception as e:
        flash(f'Error saving fee receipt: {str(e)}', 'danger')
        return redirect(url_for('fees'))

@app.route('/get_fees')
@login_required
def get_fees():
    class_id = request.args.get('class_id')
    month = request.args.get('month')
    reg_no = request.args.get('reg_no')
    
    conn = get_db()
    
    if session.get('role') == 'student' or reg_no:
        # If student and no reg_no provided, try from user_id
        if not reg_no and session.get('role') == 'student':
            student = conn.execute('SELECT reg_no FROM students WHERE user_id = ?', (session['user_id'],)).fetchone()
            reg_no = student['reg_no'] if student else None
            
        if reg_no:
            results = conn.execute('SELECT * FROM fees WHERE reg_no = ? ORDER BY payment_date DESC', (reg_no,)).fetchall()
        else:
            results = []
    else:
        # Admin or Teacher
        query = 'SELECT * FROM fees WHERE 1=1'
        params = []
        if class_id:
            query += ' AND class_id = ?'
            params.append(class_id)
        if month:
            query += ' AND month = ?'
            params.append(month)
        results = conn.execute(query, tuple(params)).fetchall()
        
    conn.close()
    return jsonify({'success': True, 'results': [dict(r) for r in results]})

@app.route('/delete_student/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        conn = get_db()
        # Find user_id if linked
        student = conn.execute('SELECT user_id, reg_no FROM students WHERE id = ?', (student_id,)).fetchone()
        if student:
            # Delete attendance and marks first due to FK or logic
            conn.execute('DELETE FROM attendance WHERE reg_no = ?', (student['reg_no'],))
            conn.execute('DELETE FROM marks WHERE reg_no = ?', (student['reg_no'],))
            conn.execute('DELETE FROM fees WHERE reg_no = ?', (student['reg_no'],))
            
            if student['user_id']:
                conn.execute('DELETE FROM users WHERE id = ?', (student['user_id'],))
            conn.execute('DELETE FROM students WHERE id = ?', (student_id,))
            conn.commit()
            flash('Student and related records deleted successfully', 'success')
        conn.close()
    except Exception as e:
        flash(f'Error deleting student: {str(e)}', 'danger')
    return redirect(url_for('attendance'))

@app.route('/delete_attendance_day', methods=['POST'])
@login_required
def delete_attendance_day():
    if not is_teacher_or_admin():
        abort(403)
    try:
        class_id = request.form.get('class_id')
        att_date = request.form.get('att_date')
        subject_id = request.form.get('subject_id')
        
        conn = get_db()
        if subject_id and subject_id != 'None' and subject_id != '':
            conn.execute('DELETE FROM attendance WHERE class_id = ? AND att_date = ? AND subject_id = ?', 
                        (class_id, att_date, subject_id))
        else:
            conn.execute('DELETE FROM attendance WHERE class_id = ? AND att_date = ? AND subject_id IS NULL', 
                        (class_id, att_date))
        conn.commit()
        conn.close()
        flash('Attendance record deleted', 'success')
    except Exception as e:
        flash(f'Error deleting attendance: {str(e)}', 'danger')
    return redirect(url_for('history'))

@app.route('/delete_mark', methods=['POST'])
@login_required
def delete_mark():
    if not is_teacher_or_admin():
        abort(403)
    try:
        data = request.get_json()
        class_id = data.get('class_id')
        subject_name = data.get('subject_name')
        exam_id = data.get('exam_id')
        reg_no = data.get('reg_no')
        
        conn = get_db()
        if reg_no:
            # Delete specific student mark
            query = '''
                DELETE FROM marks 
                WHERE class_id = ? AND exam_id = ? AND reg_no = ?
                AND subject_id IN (SELECT id FROM subjects WHERE LOWER(subject_name) = LOWER(?))
            '''
            conn.execute(query, (class_id, exam_id, reg_no, subject_name))
        else:
            # Delete all marks for this class/subject/exam
            query = '''
                DELETE FROM marks 
                WHERE class_id = ? AND exam_id = ?
                AND subject_id IN (SELECT id FROM subjects WHERE LOWER(subject_name) = LOWER(?))
            '''
            conn.execute(query, (class_id, exam_id, subject_name))
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Marks deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/delete_fee/<int:fee_id>', methods=['POST'])
@login_required
def delete_fee(fee_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        conn = get_db()
        conn.execute('DELETE FROM fees WHERE id = ?', (fee_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Fee record deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        conn = get_db()
        conn.execute('DELETE FROM marks WHERE subject_id = ?', (subject_id,))
        conn.execute('DELETE FROM attendance WHERE subject_id = ?', (subject_id,))
        conn.execute('DELETE FROM subjects WHERE id = ?', (subject_id,))
        conn.commit()
        conn.close()
        flash('Subject deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting subject: {str(e)}', 'danger')
    return redirect(url_for('attendance'))

@app.route('/delete_exam/<int:exam_id>', methods=['POST'])
@login_required
def delete_exam(exam_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        conn = get_db()
        conn.execute('DELETE FROM marks WHERE exam_id = ?', (exam_id,))
        conn.execute('DELETE FROM exams WHERE id = ?', (exam_id,))
        conn.commit()
        conn.close()
        flash('Exam and related marks deleted', 'success')
    except Exception as e:
        flash(f'Error deleting exam: {str(e)}', 'danger')
    return redirect(url_for('exam_marks'))

@app.route('/delete_class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        conn = get_db()
        # Find students in this class
        students = conn.execute('SELECT reg_no FROM students WHERE class_id = ?', (class_id,)).fetchall()
        for s in students:
            conn.execute('DELETE FROM attendance WHERE reg_no = ?', (s['reg_no'],))
            conn.execute('DELETE FROM marks WHERE reg_no = ?', (s['reg_no'],))
            conn.execute('DELETE FROM fees WHERE reg_no = ?', (s['reg_no'],))
        
        conn.execute('DELETE FROM students WHERE class_id = ?', (class_id,))
        conn.execute('DELETE FROM subjects WHERE class_id = ?', (class_id,))
        conn.execute('DELETE FROM classes WHERE id = ?', (class_id,))
        conn.commit()
        conn.close()
        flash('Class and all related records deleted', 'success')
    except Exception as e:
        flash(f'Error deleting class: {str(e)}', 'danger')
    return redirect(url_for('attendance'))

@app.route('/update_mark', methods=['POST'])
@login_required
def update_mark():
    if not is_teacher_or_admin():
        abort(403)
    try:
        data = request.get_json()
        mark_id = data.get('id')
        new_marks = data.get('marks_scored')
        
        conn = get_db()
        conn.execute('UPDATE marks SET marks_scored = ? WHERE id = ?', (new_marks, mark_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Mark updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_attendance_status', methods=['POST'])
@login_required
def update_attendance_status():
    if session.get('role') != 'admin':
        abort(403)
    try:
        data = request.get_json()
        att_id = data.get('id')
        new_status = data.get('present') # Boolean
        
        conn = get_db()
        conn.execute('UPDATE attendance SET present = ? WHERE id = ?', (new_status, att_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Attendance updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_fee_record', methods=['POST'])
@login_required
def update_fee_record():
    if session.get('role') != 'admin':
        abort(403)
    try:
        data = request.get_json()
        fee_id = data.get('id')
        month = data.get('month')
        payment_mode = data.get('payment_mode')
        balance = data.get('balance_amount')
        
        conn = get_db()
        conn.execute('''
            UPDATE fees 
            SET month = ?, payment_mode = ?, balance_amount = ? 
            WHERE id = ?
        ''', (month, payment_mode, balance, fee_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Fee record updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/profile')
@login_required
def profile():
    role = session.get('role')
    user_id = session.get('user_id')
    conn = get_db()
    profile_data = None
    
    if role == 'student':
        profile_data = conn.execute('''
            SELECT s.*, c.class_name, c.section 
            FROM students s 
            LEFT JOIN classes c ON s.class_id = c.id 
            WHERE s.user_id = ?
        ''', (user_id,)).fetchone()
    elif role == 'teacher':
        profile_data = conn.execute('SELECT * FROM teacher_profiles WHERE user_id = ?', (user_id,)).fetchone()
    elif role == 'admin':
        profile_data = conn.execute('SELECT * FROM admin_profiles WHERE user_id = ?', (user_id,)).fetchone()
        
    conn.close()
    return render_template('profile.html', profile=profile_data)

@app.route('/upload_profiles', methods=['POST'])
@login_required
def upload_profiles():
    if session.get('role') != 'admin':
        abort(403)
    
    try:
        import json
        profile_type = request.form.get('profile_type') # 'student', 'teacher', 'admin'
        data_str = request.form.get('profile_data', '').strip()
        
        if not data_str:
            flash('No profile data provided', 'danger')
            return redirect(url_for('profile'))
            
        data = json.loads(data_str)
        conn = get_db()
        
        added = 0
        updated = 0
        
        for item in data:
            if profile_type == 'student':
                reg_no = str(item.get('register_number', '')).strip()
                name = str(item.get('name', '')).strip()
                class_name = str(item.get('class', '')).strip()
                section = str(item.get('section', 'A')).strip()
                
                # Find class
                class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                        (f'Class {class_name}', section)).fetchone()
                if not class_rec:
                    conn.execute('INSERT INTO classes (class_name, section) VALUES (?, ?)',
                                (f'Class {class_name}', section))
                    conn.commit()
                    class_rec = conn.execute('SELECT id FROM classes WHERE class_name = ? AND section = ?',
                                            (f'Class {class_name}', section)).fetchone()
                
                class_id = class_rec['id']
                
                existing = conn.execute('SELECT id FROM students WHERE reg_no = ?', (reg_no,)).fetchone()
                if existing:
                    conn.execute('''
                        UPDATE students SET name = ?, class_id = ?, 
                        mother_name = ?, mother_phone = ?, father_name = ?, father_phone = ?, 
                        address = ?, dob = ?, blood_group = ?
                        WHERE reg_no = ?
                    ''', (name, class_id, item.get('mother_name'), item.get('mother_phone'), 
                          item.get('father_name'), item.get('father_phone'), 
                          item.get('address'), item.get('dob'), item.get('blood_group'), reg_no))
                    updated += 1
                else:
                    conn.execute('''
                        INSERT INTO students (reg_no, name, class_id, mother_name, mother_phone, 
                                            father_name, father_phone, address, dob, blood_group)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (reg_no, name, class_id, item.get('mother_name'), item.get('mother_phone'), 
                          item.get('father_name'), item.get('father_phone'), 
                          item.get('address'), item.get('dob'), item.get('blood_group')))
                    added += 1
                    
            elif profile_type == 'teacher':
                name = item.get('name')
                reg_id = item.get('register_id')
                main_subject = item.get('main_subject')
                advisor = item.get('class_advisor')
                
                existing = conn.execute('SELECT id FROM teacher_profiles WHERE register_id = ?', (reg_id,)).fetchone()
                if existing:
                    conn.execute('UPDATE teacher_profiles SET name = ?, main_subject = ?, class_advisor = ? WHERE register_id = ?',
                                (name, main_subject, advisor, reg_id))
                    updated += 1
                else:
                    conn.execute('INSERT INTO teacher_profiles (name, register_id, main_subject, class_advisor) VALUES (?, ?, ?, ?)',
                                (name, reg_id, main_subject, advisor))
                    added += 1
                    
            elif profile_type == 'admin':
                name = item.get('name')
                reg_id = item.get('register_id')
                main_subject = item.get('main_subject')
                advisor = item.get('class_advisor')
                role_title = item.get('role')
                
                existing = conn.execute('SELECT id FROM admin_profiles WHERE register_id = ?', (reg_id,)).fetchone()
                if existing:
                    conn.execute('''
                        UPDATE admin_profiles SET name = ?, main_subject = ?, class_advisor = ?, role_title = ? 
                        WHERE register_id = ?
                    ''', (name, main_subject, advisor, role_title, reg_id))
                    updated += 1
                else:
                    conn.execute('''
                        INSERT INTO admin_profiles (name, register_id, main_subject, class_advisor, role_title) 
                        VALUES (?, ?, ?, ?, ?)
                    ''', (name, reg_id, main_subject, advisor, role_title))
                    added += 1
        
        conn.commit()
        conn.close()
        flash(f'Successfully processed profiles: {added} added, {updated} updated', 'success')
        
    except Exception as e:
        flash(f'Error uploading profiles: {str(e)}', 'danger')
        
    return redirect(url_for('profile'))

@app.route('/timetable')
@login_required
def timetable():
    conn = get_db()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name, section').fetchall()
    
    class_id = request.args.get('class_id')
    day = request.args.get('day')
    
    timetable_data = []
    if class_id:
        query = 'SELECT * FROM timetables WHERE class_id = ?'
        params = [class_id]
        if day:
            query += ' AND day = ?'
            params.append(day)
        timetable_data = conn.execute(query, tuple(params)).fetchall()
        
    conn.close()
    return render_template('timetable.html', classes=classes, timetable=timetable_data, 
                           selected_class_id=class_id)

@app.route('/upload_timetable', methods=['POST'])
@login_required
def upload_timetable():
    if session.get('role') not in ['admin', 'teacher']:
        abort(403)
        
    try:
        class_id = request.form.get('class_id')
        day = request.form.get('day')
        subject = request.form.get('subject')
        faculty = request.form.get('faculty')
        
        if not all([class_id, day, subject, faculty]):
            flash('All fields are required', 'danger')
            return redirect(url_for('timetable'))
            
        conn = get_db()
        # Delete existing if same day and subject (or maybe same slot/period, but user didn't specify slot)
        # Assuming one entry per day per subject for now as per "Each day which subject"
        conn.execute('INSERT OR REPLACE INTO timetables (class_id, day, subject_name, faculty_name) VALUES (?, ?, ?, ?)',
                    (class_id, day, subject, faculty))
        conn.commit()
        conn.close()
        flash('Timetable entry saved successfully', 'success')
    except Exception as e:
        flash(f'Error saving timetable: {str(e)}', 'danger')
        
    return redirect(url_for('timetable'))

@app.route('/delete_timetable/<int:tt_id>', methods=['POST'])
@login_required
def delete_timetable(tt_id):
    if session.get('role') not in ['admin', 'teacher']:
        abort(403)
    try:
        conn = get_db()
        conn.execute('DELETE FROM timetables WHERE id = ?', (tt_id,))
        conn.commit()
        conn.close()
        flash('Timetable entry deleted', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('timetable'))

# Initialize database on startup
init_db()

if __name__ == '__main__':
    app.run(debug=True)
