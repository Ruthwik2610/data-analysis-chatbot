from src.agents.base import DomainAgent
from src.agents.education import EducationAgent

DOMAIN_AGENTS = {
    "education": EducationAgent
}

def get_agent_for_domain(domain: str) -> DomainAgent | None:
    agent_cls = DOMAIN_AGENTS.get(domain.lower())
    if agent_cls:
        return agent_cls()
    return None
