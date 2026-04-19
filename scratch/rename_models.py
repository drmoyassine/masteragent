import os

path = 'backend/memory_models.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace classes
text = text.replace('PrivateKnowledge', 'Intelligence')
text = text.replace('PublicKnowledge', 'Knowledge')

# Replace attributes mapping
text = text.replace('PrivateKnowledges_count', 'intelligence_count')
text = text.replace('last_PrivateKnowledge_date', 'last_intelligence_date')
text = text.replace('PrivateKnowledges_ids', 'intelligence_ids')

text = text.replace('source_PrivateKnowledge_ids', 'source_intelligence_ids')
text = text.replace('PrivateKnowledge_type', 'knowledge_type')
text = text.replace('PrivateKnowledge_auto_approve', 'intelligence_auto_approve')
text = text.replace('PrivateKnowledge_trigger_days', 'intelligence_trigger_days')
text = text.replace('lesson_auto_promote', 'knowledge_auto_promote')
text = text.replace('pii_scrub_lessons', 'pii_scrub_knowledge')
text = text.replace('public_knowledge_threshold', 'knowledge_threshold')
text = text.replace('public_knowledge_trigger_days', 'knowledge_trigger_days')

text = text.replace('"PrivateKnowledges"', '"intelligence"')
text = text.replace('"lessons"', '"knowledge"')

text = text.replace('layer: str                      # memory | PrivateKnowledge | PublicKnowledge', 'layer: str                      # memory | intelligence | knowledge')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('memory_models.py updated successfully!')
