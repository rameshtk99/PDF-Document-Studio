#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

import json
import tempfile
from pathlib import Path

from models.models import Document, PageConfig, FooterConfig
from utils.project_manager import ProjectManager

# Create project with specific text_columns
manager1 = ProjectManager(Path(tempfile.gettempdir()) / 'test_roundtrip.pdfeditor')
doc1 = manager1.new_project('test2.pdf')

cfg = PageConfig(page_number=0)
cfg.footer_config = FooterConfig(
    text_columns=[('Page 1', '')],
    font_name='Arial',
    font_size=10
)
doc1.page_configs[0] = cfg

print(f'Before save: {cfg.footer_config.text_columns}')

manager1.save()

# Load it back
manager2 = ProjectManager(Path(tempfile.gettempdir()) / 'test_roundtrip.pdfeditor')
doc2 = manager2.load()

cfg2 = doc2.page_configs[0]
print(f'After load: {cfg2.footer_config.text_columns}')

print(f'Match: {cfg.footer_config.text_columns == cfg2.footer_config.text_columns}')

# Check the JSON file
with open(Path(tempfile.gettempdir()) / 'test_roundtrip.pdfeditor') as f:
    data = json.load(f)
    print(f'JSON text_columns: {data["page_configs"]["0"]["footer_config"]["text_columns"]}')
