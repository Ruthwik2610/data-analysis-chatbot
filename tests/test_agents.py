import pytest
from src.agents import get_agent_for_domain
from src.agents.education import EducationAgent

def test_get_agent_for_domain_education():
    agent = get_agent_for_domain("education")
    assert isinstance(agent, EducationAgent)
    prompt = agent.get_system_prompt()
    assert "Education Data Analyst" in prompt
    assert len(prompt) > 0

def test_get_agent_for_domain_none():
    agent = get_agent_for_domain("non_existent_domain")
    assert agent is None

def test_education_agent_prompt():
    agent = EducationAgent()
    prompt = agent.get_system_prompt()
    assert "expert Education Data Analyst" in prompt
    assert "timetables" in prompt
