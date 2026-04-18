"""
Bridge Hub — Vector DB (ChromaDB + Semantic Search)
სემანტიკური ძიება + 168 ფაილის სრული ინდექსირება
Self-learning: ბუღალტერის შესწორებები ავტომატურად ინდექსდება

გამოყენება:
    python3 bridge_hub_vector_db.py --index   # ფაილების ინდექსირება
    python3 bridge_hub_vector_db.py --search "VAT ექსპორტი"
    python3 bridge_hub_vector_db.py --stats
"""

import os
import re
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings

# ══════════════════════════════════════════════════════════════
# კონფიგურაცია
# ══════════════════════════════════════════════════════════════

# ChromaDB ინახება ამ საქაღალდეში (FastAPI-ს გვერდით)
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "bridge_hub_knowledge"
LEARN_COLLECTION = "bridge_hub_learned"

# ფაილების საქაღალდე (სადაც 168 ფაილია)
# Windows-ზე: C:\Users\Acer\fastapi-run\fastapi-run\knowledge_files\
FILES_DIR = os.environ.get(
    "BRIDGE_HUB_FILES_DIR",
    os.path.join(os.path.dirname(__file__), "knowledge_files")
)

# Embedding მოდელი — მრავალენოვანი (ქართული ჩათვლით)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# ══════════════════════════════════════════════════════════════
# ChromaDB კლიენტი
# ══════════════════════════════════════════════════════════════

_chroma_client = None
_collection = None
_learn_collection = None
_embedder = None


def _get_embedder():
    """Embedding მოდელის ჩატვირთვა (lazy loading) — ChromaDB built-in ONNX embedder."""
    global _embedder
    if _embedder is None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        print("⏳ ChromaDB DefaultEmbeddingFunction იტვირთება...")
        _embedder = DefaultEmbeddingFunction()
        print("✅ Embedding მოდელი მზადაა")
    return _embedder


def _get_client():
    """ChromaDB კლიენტის ინიციალიზაცია."""
    global _chroma_client, _collection, _learn_collection
    if _chroma_client is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

        # მთავარი კოლექცია
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

        # Self-learning კოლექცია
        _learn_collection = _chroma_client.get_or_create_collection(
            name=LEARN_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

    return _chroma_client, _collection, _learn_collection


# ══════════════════════════════════════════════════════════════
# ტექსტის დაჭრა (Chunking)
# ══════════════════════════════════════════════════════════════

def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """ტექსტი ნაწილებად დაჭრა სემანტიკური ოვერლეპით."""
    # პარაგრაფებად დაყოფა
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += "\n" + para if current else para
        else:
            if current:
                chunks.append(current.strip())
            # Overlap: ბოლო 100 სიმბოლო გადაიტანება
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + "\n" + para if overlap_text else para

    if current.strip():
        chunks.append(current.strip())

    # ძალიან გრძელი ნაწილების დამატებითი დაჭრა
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 2:
            words = chunk.split()
            sub = []
            sub_len = 0
            for word in words:
                sub.append(word)
                sub_len += len(word) + 1
                if sub_len >= chunk_size:
                    final_chunks.append(" ".join(sub))
                    sub = sub[-20:]  # overlap
                    sub_len = sum(len(w) + 1 for w in sub)
            if sub:
                final_chunks.append(" ".join(sub))
        else:
            final_chunks.append(chunk)

    return [c for c in final_chunks if len(c) > 50]


def _read_file(filepath: str) -> Optional[str]:
    """ფაილის წაკითხვა (TXT, MD, PDF, DOCX)."""
    ext = Path(filepath).suffix.lower()
    try:
        if ext in (".txt", ".md", ".py", ".json"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(filepath) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                import subprocess
                result = subprocess.run(
                    ["pdftotext", filepath, "-"],
                    capture_output=True, text=True, timeout=30
                )
                return result.stdout
        elif ext in (".docx", ".doc"):
            try:
                from docx import Document
                doc = Document(filepath)
                return "\n".join(p.text for p in doc.paragraphs)
            except Exception:
                return None
        elif ext in (".xlsx", ".xls", ".csv"):
            import pandas as pd
            df = pd.read_excel(filepath) if ext != ".csv" else pd.read_csv(filepath)
            return df.to_string()
    except Exception as e:
        print(f"  ⚠️ ვერ წავიკითხე {filepath}: {e}")
    return None


# ══════════════════════════════════════════════════════════════
# ინდექსირება
# ══════════════════════════════════════════════════════════════

def index_files(files_dir: str = None, force_reindex: bool = False) -> dict:
    """
    ყველა ფაილის ინდექსირება ChromaDB-ში.

    Args:
        files_dir: საქაღალდე სადაც ფაილებია
        force_reindex: True = ყველაფერი თავიდან ინდექსდება
    """
    if files_dir is None:
        files_dir = FILES_DIR

    if not os.path.exists(files_dir):
        os.makedirs(files_dir, exist_ok=True)
        print(f"📁 შეიქმნა: {files_dir}")
        print(f"   → ჩასვი ფაილები ამ საქაღალდეში და გაუშვი ხელახლა")
        return {"indexed": 0, "skipped": 0, "error": "files_dir empty"}

    _, collection, _ = _get_client()
    embedder = _get_embedder()

    # ინდექსირებული ფაილების სია
    indexed_hashes = set()
    if not force_reindex:
        existing = collection.get(include=["metadatas"])
        for meta in existing.get("metadatas", []):
            if meta and "file_hash" in meta:
                indexed_hashes.add(meta["file_hash"])

    # ფაილების სია
    supported_ext = {".txt", ".md", ".pdf", ".docx", ".doc", ".xlsx", ".csv", ".py"}
    all_files = []
    for ext in supported_ext:
        all_files.extend(Path(files_dir).rglob(f"*{ext}"))

    print(f"\n📚 ნაპოვნია {len(all_files)} ფაილი {files_dir}-ში")

    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "errors": 0}

    for i, filepath in enumerate(all_files):
        filepath_str = str(filepath)
        filename = filepath.name

        # ფაილის hash (ხელახლა ინდექსირების თავიდან ასაცილებლად)
        with open(filepath_str, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        if file_hash in indexed_hashes and not force_reindex:
            stats["skipped"] += 1
            continue

        print(f"  [{i+1}/{len(all_files)}] {filename}...", end=" ")

        text = _read_file(filepath_str)
        if not text or len(text.strip()) < 100:
            print("⏭️ (ცარიელი)")
            stats["errors"] += 1
            continue

        # კატეგორიის განსაზღვრა ფაილის სახელიდან
        category = _detect_category(filename, text)

        # ტექსტის დაჭრა
        chunks = _chunk_text(text)
        if not chunks:
            print("⏭️ (chunk ვერ შეიქმნა)")
            continue

        # Embeddings + ChromaDB-ში ჩაწერა
        try:
            embeddings = list(embedder(chunks))

            ids = [f"{file_hash}_{j}" for j in range(len(chunks))]
            metadatas = [
                {
                    "source": filename,
                    "category": category,
                    "file_hash": file_hash,
                    "chunk_index": j,
                    "filepath": filepath_str,
                    "indexed_at": datetime.now().isoformat(),
                }
                for j in range(len(chunks))
            ]

            # ძველი ჩანაწერების წაშლა (თუ ფაილი განახლდა)
            try:
                old_ids = [m["id"] for m in collection.get(
                    where={"file_hash": file_hash}, include=[]
                ).get("ids", [])]
                if old_ids:
                    collection.delete(ids=old_ids)
            except Exception:
                pass

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

            stats["indexed"] += 1
            stats["chunks"] += len(chunks)
            print(f"✅ ({len(chunks)} chunk)")

        except Exception as e:
            print(f"❌ ({e})")
            stats["errors"] += 1

    print(f"\n🎉 ინდექსირება დასრულდა!")
    print(f"   ✅ ინდექსირებული: {stats['indexed']} ფაილი")
    print(f"   ⏭️ გამოტოვებული: {stats['skipped']} (უკვე ინდექსირებული)")
    print(f"   📦 სულ chunk-ები: {stats['chunks']}")
    print(f"   ❌ შეცდომები: {stats['errors']}")

    return stats


def _detect_category(filename: str, text: str) -> str:
    """კატეგორიის ავტო-განსაზღვრა."""
    fn = filename.lower()
    tx = text[:500].lower()

    if any(w in fn for w in ["tax", "საგადასახადო", "vat", "pit", "cit", "rs.ge"]):
        return "GEORGIAN_TAX"
    if any(w in fn for w in ["acca", "ifrs", "ias", "gaap", "f2", "f3", "f9"]):
        return "ACCA_IFRS"
    if any(w in fn for w in ["bridge", "hub", "balance", "1c", "ხიდი"]):
        return "BRIDGE_HUB"
    if any(w in fn for w in ["law", "სამართალი", "კოდექსი", "კანონი"]):
        return "GEORGIAN_LAW"
    if any(w in fn for w in ["payroll", "ხელფასი", "salary"]):
        return "PAYROLL"
    if any(w in tx for w in ["vat", "დღგ", "საგადასახადო"]):
        return "GEORGIAN_TAX"
    if any(w in tx for w in ["ifrs", "acca", "ias"]):
        return "ACCA_IFRS"
    return "GENERAL"


# ══════════════════════════════════════════════════════════════
# სემანტიკური ძიება
# ══════════════════════════════════════════════════════════════

def semantic_search(
    query: str,
    top_k: int = 5,
    category: str = None,
    min_score: float = 0.3,
) -> list[dict]:
    """
    სემანტიკური ძიება ChromaDB-ში.

    Args:
        query: ძიების ტექსტი (ქართული ან ინგლისური)
        top_k: მაქსიმალური შედეგების რაოდენობა
        category: კატეგორიის ფილტრი (GEORGIAN_TAX, ACCA_IFRS, BRIDGE_HUB...)
        min_score: მინიმალური სიახლოვის ქულა (0-1)
    """
    _, collection, learn_collection = _get_client()
    embedder = _get_embedder()

    # კოლექციის სიდიდის შემოწმება
    total = collection.count()
    if total == 0:
        return []

    query_embedding = list(embedder([query])[0])

    # ფილტრი კატეგორიით
    where = {"category": category} if category else None

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        print(f"⚠️ ChromaDB query error: {e}")
        return []

    # Self-learned ჩანაწერებიც ვამატებთ
    try:
        learn_total = learn_collection.count()
        if learn_total > 0:
            learn_results = learn_collection.query(
                query_embeddings=[query_embedding],
                n_results=min(3, learn_total),
                include=["documents", "metadatas", "distances"],
            )
            # შევაერთოთ
            for docs, metas, dists in zip(
                learn_results["documents"][0],
                learn_results["metadatas"][0],
                learn_results["distances"][0],
            ):
                results["documents"][0].append(docs)
                results["metadatas"][0].append(metas)
                results["distances"][0].append(dists)
    except Exception:
        pass

    # შედეგების დამუშავება
    output = []
    seen_texts = set()

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # cosine distance → similarity score
        score = round(1 - dist, 4)
        if score < min_score:
            continue

        # დუბლიკატების გამორიცხვა
        text_key = doc[:100]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        output.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "category": meta.get("category", "GENERAL"),
            "score": score,
            "chunk_index": meta.get("chunk_index", 0),
        })

    # სორტირება score-ით
    output.sort(key=lambda x: x["score"], reverse=True)
    return output[:top_k]


def hybrid_search(query: str, top_k: int = 5) -> list[dict]:
    """
    ჰიბრიდური ძიება: Semantic (ChromaDB) + Keyword (Python rules).
    საუკეთესო შედეგები ორივე მეთოდის კომბინაციით.
    """
    # 1. სემანტიკური ძიება
    semantic_results = semantic_search(query, top_k=top_k)

    # 2. Keyword ძიება Python rules-იდან
    from bridge_hub_knowledge import search_knowledge
    keyword_results = search_knowledge(query, top_k=top_k)

    # 3. შეერთება და დუბლიკატების გამორიცხვა
    combined = []
    seen = set()

    # სემანტიკური შედეგები — უფრო მაღალი პრიორიტეტი
    for r in semantic_results:
        key = r["text"][:80]
        if key not in seen:
            seen.add(key)
            combined.append({
                "text": r["text"],
                "source": r["source"],
                "category": r["category"],
                "score": r["score"],
                "method": "semantic",
            })

    # Keyword შედეგები
    for r in keyword_results:
        key = r["text"][:80]
        if key not in seen:
            seen.add(key)
            combined.append({
                "text": r["text"],
                "source": r["source"],
                "category": r["category"],
                "score": r.get("relevance", 0.7),
                "method": "keyword",
            })

    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:top_k]


def get_context_for_llm_hybrid(query: str, max_chars: int = 4000) -> str:
    """LLM-ისთვის ჰიბრიდური კონტექსტი."""
    results = hybrid_search(query, top_k=15)
    parts = []
    total = 0
    for r in results:
        text = f"[{r['category']}|{r['source']}] {r['text']}"
        if total + len(text) > max_chars:
            break
        parts.append(text)
        total += len(text)
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════
# Self-Learning — ბუღალტერის შესწორებები
# ══════════════════════════════════════════════════════════════

def learn_from_correction(
    original_text: str,
    correct_account: str,
    correct_category: str = "LEARNED",
    tenant_id: str = "global",
    note: str = "",
) -> dict:
    """
    ბუღალტერის შესწორება → ChromaDB-ში ინდექსირება.

    მაგ: AI-მ Wolt 7810-ზე მიანიჭა, ბუღალტერმა 7720-ზე გადაიტანა.
    ეს ფუნქცია ამ შესწორებას ინახავს და შემდეგ ჯერზე AI სწორად გაიმეორებს.
    """
    _, _, learn_collection = _get_client()
    embedder = _get_embedder()

    account_names = {
        "7510": "საბანკო საკომისიო", "7210": "ხელფასი", "7310": "ქირა",
        "7410": "კომუნალური", "7710": "რეკლამა", "7720": "წარმომადგენლობითი",
        "7810": "სხვა ხარჯები", "7910": "პროცენტი", "6110": "შემოსავალი",
        "3310": "დღგ", "3320": "PIT", "3330": "PAYG", "3340": "CIT",
    }
    account_name = account_names.get(correct_account, correct_account)

    # ტექსტი, რომელიც ინდექსდება
    learn_text = (
        f"ტრანზაქცია: {original_text}\n"
        f"სწორი ანგარიში: {correct_account} — {account_name}\n"
        f"შენიშვნა: {note}"
    )

    doc_id = hashlib.md5(f"{tenant_id}_{original_text}".encode()).hexdigest()
    embedding = list(embedder([learn_text])[0])

    # ძველი ჩანაწერის წაშლა
    try:
        learn_collection.delete(ids=[doc_id])
    except Exception:
        pass

    learn_collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[learn_text],
        metadatas=[{
            "source": "human_correction",
            "category": correct_category,
            "account": correct_account,
            "tenant_id": tenant_id,
            "original_text": original_text,
            "note": note,
            "learned_at": datetime.now().isoformat(),
        }],
    )

    # Python rules-შიც ვამატებთ სწრაფი ძიებისთვის
    try:
        from bridge_hub_knowledge import learn_new_rule
        learn_new_rule(original_text, correct_account, tenant_id=tenant_id, note=note)
    except Exception:
        pass

    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{original_text}' → {correct_account} ({account_name})",
        "indexed_in": "ChromaDB + Python Rules",
    }


# ══════════════════════════════════════════════════════════════
# სტატისტიკა
# ══════════════════════════════════════════════════════════════

def get_vector_stats() -> dict:
    """ChromaDB სტატისტიკა."""
    try:
        _, collection, learn_collection = _get_client()
        total = collection.count()
        learned = learn_collection.count()

        # კატეგორიების სტატისტიკა
        categories = {}
        if total > 0:
            all_meta = collection.get(include=["metadatas"])
            for meta in all_meta.get("metadatas", []):
                if meta:
                    cat = meta.get("category", "GENERAL")
                    categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_chunks": total,
            "learned_chunks": learned,
            "categories": categories,
            "chroma_dir": CHROMA_DIR,
            "embedding_model": EMBEDDING_MODEL,
            "status": "ready" if total > 0 else "empty",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bridge Hub Vector DB")
    parser.add_argument("--index", action="store_true", help="ფაილების ინდექსირება")
    parser.add_argument("--reindex", action="store_true", help="სრული ხელახლა ინდექსირება")
    parser.add_argument("--search", type=str, help="ძიება")
    parser.add_argument("--stats", action="store_true", help="სტატისტიკა")
    parser.add_argument("--dir", type=str, help="ფაილების საქაღალდე")
    parser.add_argument("--learn", nargs=3, metavar=("TEXT", "ACCOUNT", "NOTE"),
                        help="ახალი წესის სწავლება: --learn 'Wolt' '7720' 'წარმომადგენლობითი'")
    args = parser.parse_args()

    if args.index or args.reindex:
        d = args.dir or FILES_DIR
        index_files(d, force_reindex=args.reindex)

    elif args.search:
        print(f"\n🔍 ძიება: '{args.search}'\n")
        results = hybrid_search(args.search, top_k=5)
        if not results:
            print("❌ შედეგი ვერ მოიძებნა (ChromaDB ცარიელია — გაუშვი --index)")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['category']}] {r['source']} (score: {r['score']:.3f})")
            print(f"   {r['text'][:200]}\n")

    elif args.stats:
        stats = get_vector_stats()
        print("\n📊 ChromaDB სტატისტიკა:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    elif args.learn:
        text, account, note = args.learn
        result = learn_from_correction(text, account, note=note)
        print(result["message"])

    else:
        parser.print_help()
        print("\n💡 მაგალითები:")
        print("  python3 bridge_hub_vector_db.py --stats")
        print("  python3 bridge_hub_vector_db.py --index --dir ./knowledge_files")
        print("  python3 bridge_hub_vector_db.py --search 'VAT ექსპორტი'")
        print("  python3 bridge_hub_vector_db.py --learn 'Wolt' '7720' 'წარმომადგენლობითი'")
