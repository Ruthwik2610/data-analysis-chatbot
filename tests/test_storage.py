import os
import pytest
from pathlib import Path
from backend.storage import Storage

@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    return Storage(db_path)

def test_list_chats_hides_legacy_by_default_for_authenticated_users(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id=user_id)
    titles = [c["title"] for c in chats]

    assert "User Chat" in titles
    assert "Legacy Chat" not in titles
    assert len(chats) == 1


def test_list_chats_can_include_legacy_for_test_user(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id=user_id, include_legacy=True)
    titles = [c["title"] for c in chats]

    assert "User Chat" in titles
    assert "Legacy Chat" in titles
    assert len(chats) == 2

def test_list_chats_only_legacy_for_legacy_owner(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id="legacy")
    titles = [c["title"] for c in chats]
    
    assert "Legacy Chat" in titles
    assert "User Chat" not in titles
    assert len(chats) == 1

def test_create_and_list_projects(storage):
    storage.create_project(title="Project A", owner_id="user_1")
    storage.create_project(title="Project B", owner_id="user_1")
    storage.create_project(title="Project C", owner_id="user_2")
    
    user1_projects = storage.list_projects(owner_id="user_1")
    assert len(user1_projects) == 2
    titles = [p["title"] for p in user1_projects]
    assert "Project A" in titles
    assert "Project B" in titles
    
    user2_projects = storage.list_projects(owner_id="user_2")
    assert len(user2_projects) == 1
    assert user2_projects[0]["title"] == "Project C"

def test_project_title_uniqueness(storage):
    storage.create_project(title="Unique Project", owner_id="user_1")
    with pytest.raises(ValueError, match="A project with this name already exists"):
        storage.create_project(title="Unique Project", owner_id="user_1")
    
    # Different owner can have same title (if intended, though usually titles are globally unique in some systems, 
    # but here it's filtered by owner_id in project_title_exists)
    storage.create_project(title="Unique Project", owner_id="user_2")
