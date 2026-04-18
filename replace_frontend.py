import os
import re

files = [
    'frontend/src/lib/api.js',
    'frontend/src/pages/MemoryExplorerPage.jsx',
    'frontend/src/components/settings/LLMProviderSettings.jsx',
    'frontend/src/components/settings/MemorySettings.jsx'
]

replacements = [
    (r'\bInsights\b', 'Private Knowledge'),
    (r'\binsights\b', 'privateKnowledge'),
    (r'\bLessons\b', 'Public Knowledge'),
    (r'\blessons\b', 'publicKnowledge'),
    (r'\bLesson\b', 'Public Knowledge'),
    (r'\blesson\b', 'publicKnowledge'),
    (r'\bInsight\b', 'Private Knowledge'),
    (r'\binsight\b', 'privateKnowledge'),
    (r'getprivateKnowledgeAdmin', 'getPrivateKnowledgeAdmin'),
    (r'getpublicKnowledgeAdmin', 'getPublicKnowledgeAdmin'),
    (r'createpublicKnowledgeAdmin', 'createPublicKnowledgeAdmin'),
    (r'updatepublicKnowledgeAdmin', 'updatePublicKnowledgeAdmin'),
    (r'deletepublicKnowledgeAdmin', 'deletePublicKnowledgeAdmin'),
    (r'getpublicKnowledgeTypes', 'getPublicKnowledgeTypes'),
    (r'source_privateKnowledge_ids', 'source_private_knowledge_ids'),
    (r'privateKnowledge_generation', 'private_knowledge_generation'),
    (r'publicKnowledge_generation', 'public_knowledge_generation'),
    (r"'/memory/privateKnowledge'", "'/memory/private_knowledge'"),
    (r"'/memory/publicKnowledge'", "'/memory/public_knowledge'"),
    (r"'/memory/config/publicKnowledge-types'", "'/memory/config/public_knowledge_types'"),
    (r"/memory/config/publicKnowledge-types", "/memory/config/public_knowledge_types"),
    (r"/memory/publicKnowledge/\$\{id\}", "/memory/public_knowledge/\$\{id\}")
]

for fpath in files:
    if os.path.exists(fpath):
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for pattern, repl in replacements:
            content = re.sub(pattern, repl, content)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)

print('Done')
