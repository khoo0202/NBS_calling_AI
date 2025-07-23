import json
import os

# 假设 mapping.json 在当前目录
mapping_path = os.path.join(os.path.dirname(__file__), "mapping.json")

with open(mapping_path, "r", encoding="utf-8") as f:
    mapping = json.load(f)

print("✅ Loaded mapping:", mapping)
