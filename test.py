import os
import re
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# === Connect to Neon DB ===
def connect_db():
    return psycopg2.connect(DATABASE_URL)

# === Drop old tables and recreate with new structure ===
def recreate_tables(conn):
    with conn.cursor() as cur:
        # Drop ALL related tables to start fresh
        cur.execute("DROP TABLE IF EXISTS attendance_and_marks CASCADE;")
        cur.execute("DROP TABLE IF EXISTS attendance_and_marks_s1 CASCADE;")
        cur.execute("DROP TABLE IF EXISTS attendance_and_marks_s2 CASCADE;")
        cur.execute("DROP TABLE IF EXISTS students CASCADE;")
        
        print("🗑️ All old tables dropped successfully!")
        
        # Create students table with S1 and S2 CGPA columns
        cur.execute("""
            CREATE TABLE students (
                roll_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                batch TEXT,
                branch TEXT,
                cgpa_s1 FLOAT,
                cgpa_s2 FLOAT
            );
        """)
        
        # Create S1 attendance and marks table
        cur.execute("""
            CREATE TABLE attendance_and_marks_s1 (
                id SERIAL PRIMARY KEY,
                roll_no TEXT REFERENCES students(roll_no) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                attended INTEGER,
                held INTEGER,
                attendance_percentage FLOAT,
                grade TEXT,
                ratings TEXT,
                status TEXT
            );
        """)
        
        # Create S2 attendance and marks table
        cur.execute("""
            CREATE TABLE attendance_and_marks_s2 (
                id SERIAL PRIMARY KEY,
                roll_no TEXT REFERENCES students(roll_no) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                attended INTEGER,
                held INTEGER,
                attendance_percentage FLOAT,
                grade TEXT,
                ratings TEXT,
                status TEXT
            );
        """)
        
        print("✅ New tables created successfully!")
    conn.commit()

# === Extract the Subject Table from Markdown ===
def extract_subject_table(content):
    lines = content.splitlines()
    table_lines = []
    in_table = False

    for line in lines:
        if line.strip().startswith("| Course Name"):
            in_table = True
        if in_table:
            if line.strip() == "---":
                break
            table_lines.append(line)
    
    if len(table_lines) <= 2:
        return []  # No valid table found

    subjects = []
    for row in table_lines[2:]:  # Skip header and separator
        cols = [col.strip() for col in row.strip().split("|")[1:-1]]  # Remove outer '|'
        if len(cols) == 7:
            try:
                subjects.append({
                    'subject': cols[0],
                    'attended': int(float(cols[1])),
                    'held': int(float(cols[2])),
                    'percentage': float(cols[3].replace('%', '')),
                    'grade': cols[4],
                    'ratings': cols[5],
                    'status': cols[6]
                })
            except ValueError:
                continue  # Skip invalid row
    return subjects

# === Parse a Markdown File ===
def parse_markdown_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    roll_no = re.search(r"\*\*Roll No\*\*: (.+)", content).group(1).strip()
    name = re.search(r"\*\*Name\*\*: (.+)", content).group(1).strip()
    cgpa = float(re.search(r"\*\*Current CGPA\*\*: (.+)", content).group(1).strip())
    batch = re.search(r"\*\*Academic Program\*\*: (.+)", content).group(1).strip()
    branch = re.search(r"\*\*Branch\*\*: (.+)", content).group(1).strip()

    # Determine semester from file name or content
    semester = "S2" if "Even Semester" in content or file_path.name.startswith("s2_") else "S1"

    subjects = extract_subject_table(content)

    return {
        'roll_no': roll_no,
        'name': name,
        'cgpa': cgpa,
        'batch': batch,
        'branch': branch,
        'semester': semester,
        'subjects': subjects
    }

# === Insert Student & Subjects into DB ===
def insert_student_data(conn, student):
    try:
        with conn.cursor() as cur:
            # Check if student exists
            cur.execute("SELECT roll_no FROM students WHERE roll_no = %s;", (student['roll_no'],))
            student_exists = cur.fetchone() is not None
            
            if not student_exists:
                # Insert new student
                if student['semester'] == "S1":
                    cur.execute("""
                        INSERT INTO students (roll_no, name, batch, branch, cgpa_s1)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (student['roll_no'], student['name'], student['batch'], student['branch'], student['cgpa']))
                else:  # S2
                    cur.execute("""
                        INSERT INTO students (roll_no, name, batch, branch, cgpa_s2)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (student['roll_no'], student['name'], student['batch'], student['branch'], student['cgpa']))
            else:
                # Update existing student
                if student['semester'] == "S1":
                    cur.execute("""
                        UPDATE students SET cgpa_s1 = %s WHERE roll_no = %s;
                    """, (student['cgpa'], student['roll_no']))
                else:  # S2
                    cur.execute("""
                        UPDATE students SET cgpa_s2 = %s WHERE roll_no = %s;
                    """, (student['cgpa'], student['roll_no']))
            
            # Insert subjects based on semester
            if student['semester'] == "S1":
                # Clear existing S1 subjects for this student
                cur.execute("DELETE FROM attendance_and_marks_s1 WHERE roll_no = %s;", (student['roll_no'],))
                
                # Insert S1 subjects
                for subj in student['subjects']:
                    cur.execute("""
                        INSERT INTO attendance_and_marks_s1 (
                            roll_no, subject, attended, held,
                            attendance_percentage, grade, ratings, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        student['roll_no'],
                        subj['subject'], subj['attended'], subj['held'],
                        subj['percentage'], subj['grade'],
                        subj['ratings'], subj['status']
                    ))
            else:  # S2
                # Clear existing S2 subjects for this student
                cur.execute("DELETE FROM attendance_and_marks_s2 WHERE roll_no = %s;", (student['roll_no'],))
                
                # Insert S2 subjects
                for subj in student['subjects']:
                    cur.execute("""
                        INSERT INTO attendance_and_marks_s2 (
                            roll_no, subject, attended, held,
                            attendance_percentage, grade, ratings, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        student['roll_no'],
                        subj['subject'], subj['attended'], subj['held'],
                        subj['percentage'], subj['grade'],
                        subj['ratings'], subj['status']
                    ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Database error for {student['name']}: {e}")
        return False

# === Main Execution ===
def main():
    conn = connect_db()
    
    # Recreate tables with new structure
    recreate_tables(conn)

    markdown_dir = Path("markdownfiles")
    
    processed_s1 = 0
    processed_s2 = 0
    
    print("🔄 Processing S1 files...")
    # Process S1 files first
    for file in markdown_dir.glob("*.md"):
        if not file.name.startswith("s2_"):
            try:
                student_data = parse_markdown_file(file)
                print(f"📚 Parsed {len(student_data['subjects'])} S1 subjects for {student_data['name']}")
                if insert_student_data(conn, student_data):
                    print(f"✅ Inserted S1: {student_data['name']} ({student_data['roll_no']})")
                    processed_s1 += 1
            except Exception as e:
                print(f"❌ Error processing {file.name}: {e}")
    
    print(f"\n🔄 Processing S2 files...")
    # Process S2 files
    for file in markdown_dir.glob("s2_*.md"):
        try:
            student_data = parse_markdown_file(file)
            print(f"📚 Parsed {len(student_data['subjects'])} S2 subjects for {student_data['name']}")
            if insert_student_data(conn, student_data):
                print(f"✅ Inserted S2: {student_data['name']} ({student_data['roll_no']})")
                processed_s2 += 1
        except Exception as e:
            print(f"❌ Error processing {file.name}: {e}")

    # Display summary
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM students;")
            student_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM attendance_and_marks_s1;")
            s1_records = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM attendance_and_marks_s2;")
            s2_records = cur.fetchone()[0]
            
            cur.execute("SELECT roll_no, name, cgpa_s1, cgpa_s2 FROM students ORDER BY roll_no;")
            students = cur.fetchall()
            
            print(f"\n📊 Database Summary:")
            print(f"📈 Total Students: {student_count}")
            print(f"📚 S1 Subject Records: {s1_records}")
            print(f"📚 S2 Subject Records: {s2_records}")
            print(f"🔄 Successfully processed: {processed_s1} S1 files, {processed_s2} S2 files")
            
            print(f"\n👥 Student CGPA Overview:")
            for roll_no, name, cgpa_s1, cgpa_s2 in students:
                s1_cgpa = f"{cgpa_s1:.2f}" if cgpa_s1 else "N/A"
                s2_cgpa = f"{cgpa_s2:.2f}" if cgpa_s2 else "N/A"
                print(f"   {roll_no} - {name}: S1={s1_cgpa}, S2={s2_cgpa}")
    except Exception as e:
        print(f"❌ Error generating summary: {e}")

    conn.close()
    print("\n🎉 Database migration completed successfully!")

if __name__ == "__main__":
    main()