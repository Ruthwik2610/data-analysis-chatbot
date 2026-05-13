from src.agents.base import DomainAgent
from src.agents.education import EducationAgent
from src.agents.travel import TravelAgent

DOMAIN_AGENTS = {
    "travel": TravelAgent,
    "education": EducationAgent,
}

def get_agent_for_domain(domain: str) -> DomainAgent | None:
    agent_cls = DOMAIN_AGENTS.get(domain.lower())
    if agent_cls:
        return agent_cls()
    return None
