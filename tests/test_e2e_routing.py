import pytest
from backend.storage import Storage
from src.project_intelligence import detect_project_category
import backend.server as server

@pytest.fixture()
def db(tmp_path):
    storage = Storage(tmp_path / "app.sqlite")
    return storage

def test_education_routing_flow(db, monkeypatch):
    # Patch the global DB in backend.server to use our temporary test database
    monkeypatch.setattr(server, "DB", db)

    # Step 1: Write the E2E Test
    # Mock source rows with columns that should trigger education category
    source_rows = [{"columns": ["class_room", "teacher_name"]}]
    
    # Verify detect_project_category returns "education"
    category = detect_project_category(None, source_rows)
    assert category == "education"

    # Use Storage to create a project and chat
    project = db.create_project("Education Project")
    project_id = project["id"]
    
    chat = db.create_chat(title="Education Chat")
    chat_id = chat["id"]
    
    # Associate chat with project
    db.update_chat_project(chat_id, project_id)
    
    # Set the project category to "education"
    db.upsert_project_instructions(project_id, {"category": "education"})
    
    # Verify _get_view_type(chat_id) returns "timetable"
    from backend.server import _get_view_type, _get_domain_prompt
    
    view_type = _get_view_type(chat_id)
    assert view_type == "timetable"
    
    # Verify _get_domain_prompt(chat_id) contains "expert Education Data Analyst"
    domain_prompt = _get_domain_prompt(chat_id)
    assert "expert Education Data Analyst" in domain_prompt
