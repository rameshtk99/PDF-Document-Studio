import re

with open('test_stage13.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix GlobalSettings calls - remove parameters
content = content.replace(
    'GlobalSettings(\n                default_font="Arial",\n                default_font_size=12\n            )',
    'GlobalSettings()'
)
content = content.replace(
    'GlobalSettings(\n                default_font="Times",\n                default_font_size=14\n            )',
    'GlobalSettings()'
)
content = content.replace(
    'GlobalSettings(\n                default_font="Helvetica",\n                default_font_size=13\n            )',
    'GlobalSettings()'
)
content = content.replace(
    'GlobalSettings(\n                    default_font=\'Arial\',\n                    default_font_size=12\n                )',
    'GlobalSettings()'
)

# Update Document initialization calls to only use pdf_path
# Find and fix Document( calls that have page_count and global_settings
import re

# Pattern for Document with multiple parameters
pattern = r'Document\(\s*pdf_path=([^,]+),\s*page_count=\d+,\s*global_settings=GlobalSettings\([^)]*\)\s*\)'
content = re.sub(pattern, r'Document(pdf_path=\1)', content)

with open('test_stage13.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed model parameters')
