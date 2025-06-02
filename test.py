import os
import re
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# === Connect to Neon DB ===
def connect_db():
    return psycopg2.connect(DATABASE_URL)

# === Create Tables ===
def create_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                roll_no TEXT PRIMARY KEY,
                name TEXT,
                batch TEXT,
                branch TEXT,
                cgpa FLOAT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_and_marks (
                id SERIAL PRIMARY KEY,
                roll_no TEXT REFERENCES students(roll_no),
                subject TEXT,
                attended INTEGER,
                held INTEGER,
                attendance_percentage FLOAT,
                grade TEXT,
                ratings TEXT,
                status TEXT
            );
        """)
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

    roll_no = re.search(r"\\*Roll No\\*: (.+)", content).group(1).strip()
    name = re.search(r"\\*Name\\*: (.+)", content).group(1).strip()
    cgpa = float(re.search(r"\\*Current CGPA\\*: (.+)", content).group(1).strip())
    batch = re.search(r"\\*Academic Program\\*: (.+)", content).group(1).strip()
    branch = re.search(r"\\*Branch\\*: (.+)", content).group(1).strip()

    subjects = extract_subject_table(content)

    return {
        'roll_no': roll_no,
        'name': name,
        'cgpa': cgpa,
        'batch': batch,
        'branch': branch,
        'subjects': subjects
    }

# === Insert Student & Subjects into DB ===
def insert_student_data(conn, student):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO students (roll_no, name, batch, branch, cgpa)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (roll_no) DO NOTHING;
        """, (student['roll_no'], student['name'], student['batch'], student['branch'], student['cgpa']))

        for subj in student['subjects']:
            cur.execute("""
                INSERT INTO attendance_and_marks (
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

# === Main Execution ===
def main():
    conn = connect_db()
    create_tables(conn)

    markdown_dir = Path("markdownfiles")
    for file in markdown_dir.glob("*.md"):
        student_data = parse_markdown_file(file)
        print(f"Parsed {len(student_data['subjects'])} subjects for {student_data['name']}")
        insert_student_data(conn, student_data)
        print(f"Inserted: {student_data['name']} ({student_data['roll_no']})")

    conn.close()

if __name__ == "__main__":
    main()