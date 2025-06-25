from database.db_connection import DatabaseSchema
import logging
import json

logger = logging.getLogger(__name__)

def detect_chart_request(question):
    """Detect if the user is requesting a chart and what type"""
    chart_keywords = {
        'bar': ['bar chart', 'bar graph', 'column chart', 'bar plot', 'histogram'],
        'pie': ['pie chart', 'pie graph', 'pie diagram', 'donut chart', 'doughnut chart'],
        'line': ['line chart', 'line graph', 'trend chart', 'line plot', 'trend analysis'],
        'doughnut': ['doughnut chart', 'donut chart', 'ring chart'],
        'scatter': ['scatter plot', 'scatter chart', 'correlation chart'],
        'general': ['chart', 'graph', 'visualize', 'plot', 'diagram', 'visual', 'show graphically']
    }
    
    question_lower = question.lower()
    
    # Check for specific chart types first
    for chart_type, keywords in chart_keywords.items():
        if chart_type != 'general':
            for keyword in keywords:
                if keyword in question_lower:
                    logger.info(f"Detected chart request: {chart_type}")
                    return chart_type
    
    # Check for general chart request
    for keyword in chart_keywords['general']:
        if keyword in question_lower:
            logger.info("Detected general chart request")
            return 'general'
    
    return None

def generate_chart_data(question, chart_type, data):
    """Generate Chart.js configuration based on data and chart type"""
    
    logger.info(f"Generating chart data for type: {chart_type}")
    
    try:
        if not data or len(data) == 0:
            logger.warning("No data available for chart generation")
            return None
        
        # Sample record for structure analysis
        sample_record = data[0]
        logger.info(f"Sample record keys: {list(sample_record.keys())}")
        
        # Generate chart based on type and data structure
        if chart_type == 'pie' or chart_type == 'doughnut':
            return generate_pie_chart(data, chart_type)
        
        elif chart_type == 'bar':
            return generate_bar_chart(data)
        
        elif chart_type == 'line':
            return generate_line_chart(data)
        
        elif chart_type == 'scatter':
            return generate_scatter_chart(data)
        
        elif chart_type == 'general':
            # Auto-detect best chart type based on data
            return generate_auto_chart(data)
        
        return None
        
    except Exception as e:
        logger.error(f"Error generating chart data: {e}")
        return None

def generate_pie_chart(data, chart_type='pie'):
    """Generate pie/doughnut chart for grade distribution"""
    
    try:
        # Grade distribution analysis
        grade_counts = {}
        total_records = 0
        
        for record in data:
            grade = record.get('grade', None)
            if grade and grade.strip():
                grade_counts[grade] = grade_counts.get(grade, 0) + 1
                total_records += 1
        
        if not grade_counts:
            # Try alternative grade fields
            for record in data:
                for field in ['grade_s1', 'grade_s2', 'final_grade']:
                    grade = record.get(field, None)
                    if grade and grade.strip():
                        grade_counts[grade] = grade_counts.get(grade, 0) + 1
                        total_records += 1
                        break
        
        if not grade_counts:
            logger.warning("No grade data found for pie chart")
            return None
        
        # Sort by grade hierarchy
        sorted_labels = []
        sorted_data = []
        sorted_colors = []
        
        for i, grade in enumerate(DatabaseSchema.GRADE_HIERARCHY):
            if grade in grade_counts:
                grade_name = get_grade_name(grade)
                sorted_labels.append(f"{grade} ({grade_name})")
                sorted_data.append(grade_counts[grade])
                color_index = min(i, len(DatabaseSchema.GRADE_COLORS) - 1)
                sorted_colors.append(DatabaseSchema.GRADE_COLORS[color_index])
        
        # Add grades not in hierarchy
        for grade in grade_counts:
            if grade not in DatabaseSchema.GRADE_HIERARCHY:
                sorted_labels.append(f"{grade} (Other)")
                sorted_data.append(grade_counts[grade])
                sorted_colors.append('#6b7280')
        
        chart_config = {
            "type": chart_type,
            "data": {
                "labels": sorted_labels,
                "datasets": [{
                    "data": sorted_data,
                    "backgroundColor": sorted_colors,
                    "borderWidth": 2,
                    "borderColor": '#ffffff'
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {
                        "position": "bottom",
                        "labels": {
                            "padding": 20,
                            "usePointStyle": True
                        }
                    },
                    "title": {
                        "display": True,
                        "text": f"Grade Distribution ({total_records} students)",
                        "font": {
                            "size": 16,
                            "weight": "bold"
                        },
                        "padding": {
                            "top": 10,
                            "bottom": 30
                        }
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": f"function(context) {{ return context.label + ': ' + context.parsed + ' students (' + Math.round(context.parsed/{total_records}*100) + '%)'; }}"
                        }
                    }
                }
            }
        }
        
        if chart_type == 'doughnut':
            chart_config["options"]["cutout"] = '60%'
        
        return chart_config
        
    except Exception as e:
        logger.error(f"Error generating pie chart: {e}")
        return None

def generate_bar_chart(data):
    """Generate bar chart for student performance"""
    
    try:
        students = []
        values = []
        chart_label = "Performance"
        
        # Determine what to plot based on available data
        if 'cgpa_s2' in data[0]:
            # Plot S2 CGPA
            for record in data:
                if record.get('name') and record.get('cgpa_s2'):
                    name = record['name'][:20] + "..." if len(record['name']) > 20 else record['name']
                    students.append(name)
                    values.append(float(record['cgpa_s2']))
            chart_label = "Semester 2 CGPA"
            
        elif 'cgpa_s1' in data[0]:
            # Plot S1 CGPA
            for record in data:
                if record.get('name') and record.get('cgpa_s1'):
                    name = record['name'][:20] + "..." if len(record['name']) > 20 else record['name']
                    students.append(name)
                    values.append(float(record['cgpa_s1']))
            chart_label = "Semester 1 CGPA"
            
        elif 'cgpa' in data[0]:
            # Plot general CGPA
            for record in data:
                if record.get('name') and record.get('cgpa'):
                    name = record['name'][:20] + "..." if len(record['name']) > 20 else record['name']
                    students.append(name)
                    values.append(float(record['cgpa']))
            chart_label = "CGPA"
            
        elif 'attendance_percentage' in data[0]:
            # Plot attendance
            for record in data:
                if record.get('name') and record.get('attendance_percentage'):
                    name = record['name'][:20] + "..." if len(record['name']) > 20 else record['name']
                    students.append(name)
                    values.append(float(record['attendance_percentage']))
            chart_label = "Attendance %"
        
        if not students or not values:
            logger.warning("No suitable data found for bar chart")
            return None
        
        # Limit to top 15 records for readability
        if len(students) > 15:
            students = students[:15]
            values = values[:15]
        
        return {
            "type": "bar",
            "data": {
                "labels": students,
                "datasets": [{
                    "label": chart_label,
                    "data": values,
                    "backgroundColor": generate_gradient_colors(len(values)),
                    "borderColor": '#4f46e5',
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"{chart_label} - Top {len(students)} Students",
                        "font": {"size": 16, "weight": "bold"}
                    },
                    "legend": {
                        "display": False
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 10 if 'cgpa' in chart_label.lower() else 100,
                        "title": {
                            "display": True,
                            "text": chart_label
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating bar chart: {e}")
        return None

def generate_line_chart(data):
    """Generate line chart for semester progression"""
    
    try:
        # Check if we have both S1 and S2 data
        students_with_both = []
        s1_values = []
        s2_values = []
        
        for record in data:
            if (record.get('name') and 
                record.get('cgpa_s1') is not None and 
                record.get('cgpa_s2') is not None):
                
                name = record['name'][:15] + "..." if len(record['name']) > 15 else record['name']
                students_with_both.append(name)
                s1_values.append(float(record['cgpa_s1']))
                s2_values.append(float(record['cgpa_s2']))
        
        if not students_with_both:
            logger.warning("No semester progression data found for line chart")
            return None
        
        # Limit to 12 students for readability
        if len(students_with_both) > 12:
            students_with_both = students_with_both[:12]
            s1_values = s1_values[:12]
            s2_values = s2_values[:12]
        
        return {
            "type": "line",
            "data": {
                "labels": students_with_both,
                "datasets": [
                    {
                        "label": "Semester 1 CGPA",
                        "data": s1_values,
                        "borderColor": '#ef4444',
                        "backgroundColor": 'rgba(239, 68, 68, 0.1)',
                        "tension": 0.4,
                        "fill": False,
                        "pointRadius": 4,
                        "pointHoverRadius": 6
                    },
                    {
                        "label": "Semester 2 CGPA",
                        "data": s2_values,
                        "borderColor": '#10b981',
                        "backgroundColor": 'rgba(16, 185, 129, 0.1)',
                        "tension": 0.4,
                        "fill": False,
                        "pointRadius": 4,
                        "pointHoverRadius": 6
                    }
                ]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"CGPA Progression (S1 → S2) - {len(students_with_both)} Students",
                        "font": {"size": 16, "weight": "bold"}
                    },
                    "legend": {
                        "position": "top"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 10,
                        "title": {
                            "display": True,
                            "text": "CGPA (O=10, A+=9, A=8, etc.)"
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating line chart: {e}")
        return None

def generate_scatter_chart(data):
    """Generate scatter plot for correlation analysis"""
    
    try:
        scatter_data = []
        
        # Correlate attendance with CGPA
        for record in data:
            attendance = record.get('attendance_percentage')
            cgpa = record.get('cgpa_s2') or record.get('cgpa_s1') or record.get('cgpa')
            
            if attendance is not None and cgpa is not None:
                scatter_data.append({
                    "x": float(attendance),
                    "y": float(cgpa)
                })
        
        if len(scatter_data) < 3:
            logger.warning("Insufficient data for scatter plot")
            return None
        
        return {
            "type": "scatter",
            "data": {
                "datasets": [{
                    "label": "Attendance vs CGPA",
                    "data": scatter_data,
                    "backgroundColor": 'rgba(59, 130, 246, 0.6)',
                    "borderColor": '#3b82f6',
                    "pointRadius": 5
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Attendance vs CGPA Correlation ({len(scatter_data)} students)",
                        "font": {"size": 16, "weight": "bold"}
                    }
                },
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": "Attendance %"
                        },
                        "min": 0,
                        "max": 100
                    },
                    "y": {
                        "title": {
                            "display": True,
                            "text": "CGPA"
                        },
                        "min": 0,
                        "max": 10
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating scatter chart: {e}")
        return None

def generate_auto_chart(data):
    """Auto-detect best chart type based on data structure"""
    
    try:
        sample = data[0]
        
        # If we have grade data, show pie chart
        if 'grade' in sample:
            return generate_pie_chart(data, 'pie')
        
        # If we have both semester CGPAs, show line chart
        elif 'cgpa_s1' in sample and 'cgpa_s2' in sample:
            return generate_line_chart(data)
        
        # If we have student names and performance data, show bar chart
        elif 'name' in sample and ('cgpa' in sample or 'cgpa_s1' in sample or 'cgpa_s2' in sample):
            return generate_bar_chart(data)
        
        # Default to bar chart
        else:
            return generate_bar_chart(data)
            
    except Exception as e:
        logger.error(f"Error in auto chart generation: {e}")
        return None

def get_grade_name(grade):
    """Get descriptive name for grade"""
    grade_names = {
        'O': 'Outstanding',
        'A+': 'Excellent', 
        'A': 'Very Good',
        'B+': 'Good',
        'B': 'Above Average',
        'C+': 'Below Average',
        'C': 'Average',
        'D+': 'Poor',
        'D': 'Poor',
        'F': 'Fail'
    }
    return grade_names.get(grade, grade)

def generate_gradient_colors(count):
    """Generate gradient colors for charts"""
    colors = [
        '#8b5cf6', '#a855f7', '#c084fc', '#d8b4fe',
        '#3b82f6', '#60a5fa', '#93c5fd', '#dbeafe',
        '#10b981', '#34d399', '#6ee7b7', '#a7f3d0',
        '#f59e0b', '#fbbf24', '#fcd34d', '#fde68a'
    ]
    
    return colors[:count] if count <= len(colors) else colors * ((count // len(colors)) + 1)

def validate_chart_data(chart_config):
    """Validate chart configuration before sending to frontend"""
    
    try:
        required_fields = ['type', 'data', 'options']
        
        for field in required_fields:
            if field not in chart_config:
                logger.error(f"Missing required field in chart config: {field}")
                return False
        
        if 'datasets' not in chart_config['data']:
            logger.error("Missing datasets in chart data")
            return False
        
        if not chart_config['data']['datasets']:
            logger.error("Empty datasets in chart data")
            return False
        
        logger.info("Chart configuration validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Error validating chart data: {e}")
        return False