from typing_extensions import List, TypedDict

class MultiAgentState(TypedDict):
    question: str
    chat_history: List[dict]
    generated_prompt: str
    sql_query: str
    retrieved_data: List[dict]
    formatted_context: str
    answer: str
    suggested_questions: str
    parent_student_id: str
    access_denied: bool
    user_type: str
    chart_data: dict