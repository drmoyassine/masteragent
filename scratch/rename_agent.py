import os

path = 'backend/memory/agent.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Models
text = text.replace('PrivateKnowledge', 'Intelligence')
text = text.replace('PublicKnowledge', 'Knowledge')

# Routes
text = text.replace('/private_knowledge', '/intelligence')
text = text.replace('/public_knowledge', '/knowledge')

# Tags
text = text.replace('\"💡 private_knowledge\"', '\"💡 Intelligence\"')
text = text.replace('\"🎓 public_knowledge\"', '\"🎓 Knowledge\"')

# Function params & names
text = text.replace('private_knowledge_ids', 'intelligence_ids')
text = text.replace('source_private_knowledge_ids', 'source_intelligence_ids')

# Replace the specific hardcoded ContextStatusResponse assignments that we manually fixed earlier
text = text.replace('PrivateKnowledges_count', 'intelligence_count')
text = text.replace('last_PrivateKnowledge_date', 'last_intelligence_date')
text = text.replace('PrivateKnowledges_ids', 'intelligence_ids')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('agent.py updated successfully!')
