import os, uuid
from datetime import datetime, timezone

_db = None

def get_db():
    global _db
    if _db is None:
        try:
            from google.cloud import firestore
            _db = firestore.Client(project=os.getenv("GCP_PROJECT_ID"))
        except Exception as e:
            print(f"[Firestore] {e}")
    return _db

def contacts_save(contact):
    db = get_db()
    if not db: return {"ok": True, "mode": "mock", "id": contact.get("id", str(uuid.uuid4()))}
    try:
        cid = contact.get("id") or str(uuid.uuid4())
        contact["id"] = cid
        contact["updated_at"] = datetime.now(timezone.utc).isoformat()
        db.collection("contacts").document(cid).set(contact)
        return {"ok": True, "id": cid}
    except Exception as e:
        return {"ok": False, "error": str(e), "id": str(uuid.uuid4())}

def contacts_list():
    db = get_db()
    if not db: return []
    try:
        return [d.to_dict() for d in db.collection("contacts").stream()]
    except: return []

def contacts_search(query):
    all_c = contacts_list()
    if not query: return all_c
    q = query.lower().strip()
    results = []
    for c in all_c:
        name = (c.get("name") or "").lower()
        email = (c.get("email") or "").lower()
        company = (c.get("company") or "").lower()
        score = 0
        if q == name: score = 100
        elif q in name: score = 80
        elif name.startswith(q): score = 70
        elif any(p in name for p in q.split()): score = 50
        elif q in email or q in company: score = 30
        if score > 0: results.append({**c, "_score": score})
    return sorted(results, key=lambda x: x["_score"], reverse=True)

def contacts_resolve_email(name_or_email):
    if "@" in name_or_email: return name_or_email
    r = contacts_search(name_or_email)
    return r[0].get("email") if r else None

def audit_log(event):
    db = get_db()
    if not db: return
    try:
        event["_logged_at"] = datetime.now(timezone.utc).isoformat()
        db.collection("audit_trail").document(str(uuid.uuid4())).set(event)
    except: pass

def audit_list(limit=50):
    db = get_db()
    if not db: return []
    try:
        docs = db.collection("audit_trail").order_by("_logged_at", direction="DESCENDING").limit(limit).stream()
        return [d.to_dict() for d in docs]
    except: return []
