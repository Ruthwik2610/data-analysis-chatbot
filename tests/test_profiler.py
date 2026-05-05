from src.project_intelligence import detect_project_category

def test_detect_project_category_education_columns():
    # Test that having "teacher", "timetable", or "class" in column names triggers "education" category
    project = {"title": "My Data"}
    # Simulated source_rows where columns are passed as part of the row description
    # filename "data.csv" has no keywords.
    source_rows = [
        {
            "name": "data.csv",
            "kind": "csv",
            "columns": ["id", "teacher_name", "class_room", "timetable_id"]
        }
    ]
    
    category = detect_project_category(project, source_rows)
    assert category == "education"

def test_detect_project_category_general():
    project = {"title": "My Data"}
    source_rows = [
        {
            "name": "data.csv",
            "kind": "csv",
            "columns": ["id", "value"]
        }
    ]
    category = detect_project_category(project, source_rows)
    assert category == "general"
