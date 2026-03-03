import json, os, requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://127.0.0.1:8080")

def almost_equal(a, b, eps=0.01):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= eps

def main():
    path = "examples/email_invoice_cases.jsonl"
    total = ok_vendor = ok_amount = ok_currency = ok_all = 0
    fallback_used = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            total += 1

            payload = {
                "from_field": ex.get("from"),
                "subject": ex.get("subject"),
                "body": ex.get("body"),
            }

            r = requests.post(f"{SERVICE_URL}/bridge/demo/email_invoice", json=payload, timeout=60)
            r.raise_for_status()
            res = r.json().get("result", {})
            exp = ex.get("expected", {})

            v_ok = (res.get("vendor") is not None and str(res.get("vendor")).strip() != "")
            a_ok = almost_equal(res.get("amount"), exp.get("amount"))
            c_ok = (res.get("currency") or "").upper() == (exp.get("currency") or "").upper()

            ok_vendor += 1 if v_ok else 0
            ok_amount += 1 if a_ok else 0
            ok_currency += 1 if c_ok else 0
            ok_all += 1 if (v_ok and a_ok and c_ok) else 0

            if res.get("source") in ("llm", "hybrid"):
                fallback_used += 1

            if not (v_ok and a_ok and c_ok):
                print(f"[FAIL] {ex.get('id')}: got={res} expected={exp}")

    print("\n---- REPORT ----")
    print("total:", total)
    print("vendor_present:", f"{ok_vendor}/{total}")
    print("amount_match:", f"{ok_amount}/{total}")
    print("currency_match:", f"{ok_currency}/{total}")
    print("all_ok:", f"{ok_all}/{total}")
    print("fallback_used:", f"{fallback_used}/{total}")

if __name__ == "__main__":
    main()
