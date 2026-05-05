class DomainAgent:
    def __init__(self, domain: str):
        self.domain = domain
    def get_system_prompt(self) -> str:
        return ""
    def get_tools(self) -> list[dict]:
        return []
