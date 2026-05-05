from src.agents.base import DomainAgent

class EducationAgent(DomainAgent):
    def __init__(self):
        super().__init__(domain="education")
    
    def get_system_prompt(self) -> str:
        return (
            "You are an expert Education Data Analyst. "
            "You specialize in school timetables, scheduling, teacher assignments, and student enrollments. "
            "When analyzing data, prioritize pedagogical efficiency and balanced workloads."
        )
