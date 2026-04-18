import os
import re

scan_dirs = ["backend", "frontend/src"]

replacements = [
    (r'InsightCreate', 'PrivateKnowledgeCreate'),
    (r'InsightUpdate', 'PrivateKnowledgeUpdate'),
    (r'InsightResponse', 'PrivateKnowledgeResponse'),
    (r'LessonCreate', 'PublicKnowledgeCreate'),
    (r'LessonUpdate', 'PublicKnowledgeUpdate'),
    (r'LessonResponse', 'PublicKnowledgeResponse'),
    
    (r'search_insights_by_vector', 'search_private_knowledge_by_vector'),
    (r'search_insights_by_fulltext', 'search_private_knowledge_by_fulltext'),
    (r'search_lessons_by_vector', 'search_public_knowledge_by_vector'),
    (r'search_lessons_by_fulltext', 'search_public_knowledge_by_fulltext'),
    
    (r'insights_count', 'private_knowledge_count'),
    (r'insights_ids', 'private_knowledge_ids'),
    (r'last_insight_date', 'last_private_knowledge_date'),
    (r'create_insight', 'create_private_knowledge'),
    (r'update_insight', 'update_private_knowledge'),
    (r'delete_insight', 'delete_private_knowledge'),
    (r'list_insights', 'list_private_knowledge'),

    (r'lessons_count', 'public_knowledge_count'),
    (r'lessons_ids', 'public_knowledge_ids'),
    (r'last_lesson_date', 'last_public_knowledge_date'),
    (r'create_lesson', 'create_public_knowledge'),
    (r'update_lesson', 'update_public_knowledge'),
    (r'delete_lesson', 'delete_public_knowledge'),
    (r'list_lessons', 'list_public_knowledge')
]

for root_dir in scan_dirs:
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f.endswith('.py') or f.endswith('.js') or f.endswith('.jsx'):
                fpath = os.path.join(dirpath, f)
                with open(fpath, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                original = content
                for pattern, repl in replacements:
                    content = re.sub(pattern, repl, content)
                
                if content != original:
                    with open(fpath, 'w', encoding='utf-8') as file:
                        file.write(content)
                    print(f"Updated {fpath}")

print('Done')
