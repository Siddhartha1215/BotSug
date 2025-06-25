import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(Config.DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

class DatabaseSchema:
    """Database schema information"""
    
    SCHEMA_CONTEXT = """
    Database Schema:
    
    Table: students
    - roll_no (TEXT PRIMARY KEY) - Student roll number like 'AM.AR.U316BCA001'
    - name (TEXT) - Student full name
    - batch (TEXT) - Academic program/batch like 'BCA2016'
    - branch (TEXT) - Branch like 'Bachelor of Computer Applications'
    - cgpa_s1 (FLOAT) - Semester 1 CGPA
    - cgpa_s2 (FLOAT) - Semester 2 CGPA
    
    Table: attendance_and_marks_s1 (Semester 1 Data)
    - id (SERIAL PRIMARY KEY)
    - roll_no (TEXT) - References students(roll_no)
    - subject (TEXT) - Subject name (Cultural Education I, Communicative English, etc.)
    - attended (INTEGER) - Classes attended
    - held (INTEGER) - Total classes held
    - attendance_percentage (FLOAT) - Attendance percentage
    - grade (TEXT) - Grade obtained (A, B, C, etc.)
    - ratings (TEXT) - Performance ratings (Good, Average, Poor, etc.)
    - status (TEXT) - Pass/Fail status
    
    Table: attendance_and_marks_s2 (Semester 2 Data)
    - id (SERIAL PRIMARY KEY)
    - roll_no (TEXT) - References students(roll_no)
    - subject (TEXT) - Subject name (Cultural Education II, Professional Communication, etc.)
    - attended (INTEGER) - Classes attended
    - held (INTEGER) - Total classes held
    - attendance_percentage (FLOAT) - Attendance percentage
    - grade (TEXT) - Grade obtained (A, B, C, etc.)
    - ratings (TEXT) - Performance ratings (Good, Average, Poor, etc.)
    - status (TEXT) - Pass/Fail status
    
    Important Notes:
    - Use 's' for students table alias
    - Use 'am_s1' for attendance_and_marks_s1 table alias
    - Use 'am_s2' for attendance_and_marks_s2 table alias
    - Students have separate CGPA for each semester (cgpa_s1, cgpa_s2)
    - Attendance and marks are stored separately for S1 and S2
    - When querying both semesters, use UNION or separate joins
    """
    
    GRADE_HIERARCHY = ['O', 'A+', 'A', 'B+', 'B', 'C+', 'C', 'D+', 'D', 'F']
    GRADE_COLORS = ['#10b981', '#059669', '#0d9488', '#0891b2', '#0284c7', '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#ef4444']
    
    @staticmethod
    def get_grade_hierarchy_context():
        return """
        Grade Hierarchy (Highest to Lowest):
        - O (Outstanding) - Highest grade (10 points)
        - A+ (Excellent) - (9 points)
        - A (Very Good) - (8 points)
        - B+ (Good) - (7 points)
        - B (Above Average) - (6 points)
        - C+ (Below Average) - (5 points)
        - C (Average) - (4 points)
        - D+ (Poor) - (3 points)
        - D (Poor) - (2 points)
        - F (Fail) - (0 points)
        """