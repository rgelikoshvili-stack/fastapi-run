import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge_files")
os.environ["BRIDGE_HUB_FILES_DIR"] = KNOWLEDGE_DIR

from bridge_hub_vector_db import index_files, get_vector_stats

print("=" * 60)
print("Bridge Hub — ფაილების ინდექსირება ChromaDB-ში")
print("=" * 60)
print(f"📁 საქაღალდე: {KNOWLEDGE_DIR}")

file_count = len([f for f in os.listdir(KNOWLEDGE_DIR)
                  if os.path.isfile(os.path.join(KNOWLEDGE_DIR, f))])
print(f"📄 ფაილები: {file_count}")
print()

stats = index_files(files_dir=KNOWLEDGE_DIR, force_reindex=False)

print()
print("=" * 60)
print(f"✅ ინდექსირებული: {stats.get('indexed', 0)}")
print(f"⏭️  გამოტოვებული: {stats.get('skipped', 0)}")
print(f"📄 Chunks: {stats.get('chunks', 0)}")
print(f"❌ შეცდომები: {stats.get('errors', 0)}")

vstats = get_vector_stats()
print(f"\n📊 ChromaDB: {vstats.get('total_chunks', 0)} chunk")
print("=" * 60)