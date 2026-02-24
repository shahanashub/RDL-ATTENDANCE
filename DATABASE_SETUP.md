# Database Setup Documentation

## Overview
Your Scientia attendance management application now has a complete, robust SQLite database setup that ensures all data is properly persisted.

## Database Configuration

### Database Engine
- **Type:** SQLite3
- **Database File:** `scientia.db` (automatically created on first run)
- **Location:** Project root directory

### Database Tables

#### 1. **users** table
Stores user account information (teachers, admins, students)
```
- id: INTEGER PRIMARY KEY (auto-increment)
- username: TEXT UNIQUE (required)
- password: TEXT (SHA256 hashed)
- role: TEXT (teacher, admin, student)
- created_at: TIMESTAMP (automatic)
```

#### 2. **classes** table
Stores class and section information
```
- id: INTEGER PRIMARY KEY (auto-increment)
- class_name: TEXT (e.g., "Class 10", "Class 11")
- section: TEXT (e.g., "A", "B", "C", "D")
- UNIQUE(class_name, section) constraint
- created_at: TIMESTAMP (automatic)
```

#### 3. **students** table
Stores student information with class assignment
```
- id: INTEGER PRIMARY KEY (auto-increment)
- reg_no: TEXT UNIQUE (registration number)
- name: TEXT (student name)
- class_id: INTEGER FOREIGN KEY (references classes.id)
- user_id: INTEGER UNIQUE FOREIGN KEY (references users.id)
- created_at: TIMESTAMP (automatic)
```

#### 4. **attendance** table
Stores attendance records
```
- id: INTEGER PRIMARY KEY (auto-increment)
- class_id: INTEGER FOREIGN KEY (references classes.id)
- att_date: DATE (attendance date)
- reg_no: TEXT (student registration number)
- present: BOOLEAN (attendance status)
- UNIQUE(class_id, att_date, reg_no) constraint
- created_at: TIMESTAMP (automatic)
```

## Data Flow

### User Registration
1. User submits registration form
2. User account is created in `users` table
3. If student role: Student record created in `students` table
4. All data persisted immediately with transaction commits

### Attendance Management
1. Teacher/Admin selects class and date
2. Students are retrieved from database
3. Teacher marks attendance via checkboxes
4. Attendance records are:
   - Deleted for existing date/class combination (replacement)
   - Created for all students (present/absent status)
5. All changes committed to database

### Student Upload (CSV)
1. Admin uploads CSV file with student data
2. Classes are created/verified in database
3. Students are inserted or updated
4. All operations committed to database
5. Prevents duplicate registration numbers

### Attendance History
1. Query retrieves all attendance dates for a class
2. For each date, fetch attendance records
3. Display complete historical data from database

## Database Features

### Data Integrity
- **Foreign Key Constraints:** Enabled (PRAGMA foreign_keys = ON)
- **Unique Constraints:** Prevent duplicate usernames, registration numbers
- **Timestamps:** Track when records are created
- **Transaction Support:** All operations are atomic (commit/rollback)

### Error Handling
- Proper exception handling for database operations
- User-friendly error messages
- Validation before data insertion
- Graceful connection closure on errors

### Sample Data
On first initialization, the database includes:
- 2 default users (teacher1, admin1)
- 3 classes (Class 10-A, Class 10-B, Class 11-A)
- 4 sample students for testing

## Requirements

Install required packages:
```bash
python -m pip install -r requirements.txt
```

### Required Packages (in requirements.txt)
- Flask==2.3.0
- Werkzeug==2.3.0
- python-dotenv==1.0.0

## Running the Application

```bash
python app.py
```

The application will:
1. Automatically initialize the database on first run
2. Create all necessary tables
3. Insert sample data if tables are empty
4. Enable foreign key constraints
5. Print confirmation message: "✓ Database initialized successfully"

## Data Persistence Guarantee

✓ All user registrations are stored
✓ All student information is stored
✓ All attendance records are stored
✓ All class information is stored
✓ Login credentials are securely hashed (SHA256)
✓ Historical data is preserved
✓ No data is lost on application restart

## Backup Recommendation

The SQLite database file `scientia.db` contains all application data. 
Regular backups are recommended by copying this file to a safe location.

---
**Last Updated:** February 18, 2026
**Application:** Scientia - Attendance Management System
