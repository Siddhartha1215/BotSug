from database.db_connection import DatabaseSchema

def analyze_retrieved_data(retrieved_data):
    """Analyze the retrieved data to understand its structure and content"""
    if not retrieved_data:
        return "No data retrieved"
    
    analysis = []
    sample_record = retrieved_data[0]
    
    # Check what type of data we have - updated for new schema
    has_cgpa_s1 = 'cgpa_s1' in sample_record
    has_cgpa_s2 = 'cgpa_s2' in sample_record
    has_cgpa = 'cgpa' in sample_record  # For backward compatibility
    has_attendance = 'attendance_percentage' in sample_record
    has_grades = 'grade' in sample_record
    has_subjects = 'subject' in sample_record
    has_names = 'name' in sample_record
    has_branches = 'branch' in sample_record
    
    # Analyze S1 CGPA
    if has_cgpa_s1:
        cgpa_s1_values = [float(r.get('cgpa_s1', 0)) for r in retrieved_data if r.get('cgpa_s1')]
        if cgpa_s1_values:
            avg_cgpa_s1 = sum(cgpa_s1_values) / len(cgpa_s1_values)
            analysis.append(f"S1 CGPA data: {len(cgpa_s1_values)} students, average S1 CGPA: {avg_cgpa_s1:.2f}")
    
    # Analyze S2 CGPA
    if has_cgpa_s2:
        cgpa_s2_values = [float(r.get('cgpa_s2', 0)) for r in retrieved_data if r.get('cgpa_s2')]
        if cgpa_s2_values:
            avg_cgpa_s2 = sum(cgpa_s2_values) / len(cgpa_s2_values)
            analysis.append(f"S2 CGPA data: {len(cgpa_s2_values)} students, average S2 CGPA: {avg_cgpa_s2:.2f}")
    
    # Legacy CGPA field (for backward compatibility)
    if has_cgpa and not has_cgpa_s1 and not has_cgpa_s2:
        cgpa_values = [float(r.get('cgpa', 0)) for r in retrieved_data if r.get('cgpa')]
        if cgpa_values:
            avg_cgpa = sum(cgpa_values) / len(cgpa_values)
            analysis.append(f"CGPA data: {len(cgpa_values)} students, average CGPA: {avg_cgpa:.2f}")
    
    if has_attendance:
        attendance_values = [float(r.get('attendance_percentage', 0)) for r in retrieved_data if r.get('attendance_percentage')]
        if attendance_values:
            avg_attendance = sum(attendance_values) / len(attendance_values)
            analysis.append(f"Attendance data: average {avg_attendance:.1f}%")
    
    if has_grades:
        grades = [r.get('grade') for r in retrieved_data if r.get('grade')]
        grade_counts = {}
        
        for grade in grades:
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
        
        # Sort grades by hierarchy for better presentation
        sorted_grade_counts = {}
        for grade in DatabaseSchema.GRADE_HIERARCHY:
            if grade in grade_counts:
                sorted_grade_counts[grade] = grade_counts[grade]
        
        # Add any grades not in hierarchy (edge cases)
        for grade in grade_counts:
            if grade not in DatabaseSchema.GRADE_HIERARCHY:
                sorted_grade_counts[grade] = grade_counts[grade]
        
        analysis.append(f"Grade distribution (O=Outstanding, A+=Excellent): {sorted_grade_counts}")
    
    if has_subjects:
        subjects = list(set([r.get('subject') for r in retrieved_data if r.get('subject')]))
        analysis.append(f"Subjects included: {len(subjects)} ({', '.join(subjects[:3])}{'...' if len(subjects) > 3 else ''})")
    
    if has_branches:
        branches = list(set([r.get('branch') for r in retrieved_data if r.get('branch')]))
        analysis.append(f"Branches: {', '.join(branches)}")
    
    analysis.append(f"Total records: {len(retrieved_data)}")
    
    return "; ".join(analysis)