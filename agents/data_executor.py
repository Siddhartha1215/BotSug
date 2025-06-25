from database.db_connection import get_db_connection
import logging

logger = logging.getLogger(__name__)

def data_executor_agent(state):
    """Agent 2: Execute SQL query and retrieve data"""
    sql_query = state["sql_query"]
    user_type = state.get("user_type", "faculty")
    parent_student_id = state.get("parent_student_id", None)
    
    logger.info(f"=== DATA EXECUTOR AGENT ===")
    logger.info(f"Executing SQL: {sql_query}")
    
    # Check for access denied query
    if "ACCESS_DENIED" in sql_query:
        logger.warning(f"Access denied for parent user: {parent_student_id}")
        return {
            "retrieved_data": [{"error": "ACCESS_DENIED", "message": f"You can only access information about your child (ID: {parent_student_id}) or general class statistics without individual student details."}],
            "access_denied": True
        }
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Additional security check for parent users
            if user_type == "parent" and parent_student_id:
                # Check if query contains individual student data for other students
                sql_lower = sql_query.lower()
                
                # If query selects individual names/roll_nos but doesn't restrict to their child
                if ("s.name" in sql_lower or "s.roll_no" in sql_lower) and parent_student_id not in sql_query:
                    # Check if it's not an aggregated query
                    if not any(agg in sql_lower for agg in ["avg(", "count(", "sum(", "max(", "min(", "group by"]):
                        logger.warning(f"Blocking parent query that accesses individual student data: {sql_query}")
                        return {
                            "retrieved_data": [{"error": "ACCESS_DENIED", "message": "You cannot access individual student details. You can only view your child's information or general class statistics."}],
                            "access_denied": True
                        }
                
                # Ensure parent-specific queries are properly restricted
                if parent_student_id not in sql_query and not any(agg in sql_lower for agg in ["avg(", "count(", "sum(", "max(", "min("]):
                    logger.info(f"Adding parent restriction to query")
                    if "WHERE" in sql_query.upper():
                        sql_query = sql_query + f" AND s.roll_no = '{parent_student_id}'"
                    else:
                        sql_query = sql_query + f" WHERE s.roll_no = '{parent_student_id}'"
                    logger.info(f"Modified SQL for parent access: {sql_query}")
            
            cur.execute(sql_query)
            results = cur.fetchall()
            
            # Convert to list of dictionaries
            retrieved_data = [dict(row) for row in results]
            
            # Print fetched records for debugging
            logger.info(f"=== FETCHED RECORDS FROM NEON DB ===")
            logger.info(f"Total records retrieved: {len(retrieved_data)}")
            
            if retrieved_data:
                logger.info("Sample records (first 3):")
                for i, record in enumerate(retrieved_data[:3], 1):
                    logger.info(f"Record {i}: {dict(record)}")
                
                # Print column names
                column_names = list(retrieved_data[0].keys()) if retrieved_data else []
                logger.info(f"Column names: {column_names}")
            else:
                logger.info("No records found in database")
            
            return {"retrieved_data": retrieved_data}
            
    except Exception as e:
        logger.error(f"Error in Data Executor Agent: {e}")
        # Return empty data on error
        return {"retrieved_data": [], "access_denied": False}
    finally:
        if 'conn' in locals():
            conn.close()