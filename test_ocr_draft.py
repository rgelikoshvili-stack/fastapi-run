import urllib.request
import json

boundary = "----BridgeHubBoundary"
with open("test_invoice.pdf", "rb") as f:
    file_data = f.read()

sep = f"--{boundary}\r\n".encode()
end = f"--{boundary}--\r\n".encode()
disposition = b"Content-Disposition: form-data; name=\"file\"; filename=\"test_invoice.pdf\"\r\n"
ctype = b"Content-Type: application/pdf\r\n\r\n"

body = sep + disposition + ctype + file_data + b"\r\n" + end

req = urllib.request.Request(
    "http://127.0.0.1:8000/ocr/extract-and-draft",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST"
)

with urllib.request.urlopen(req) as r:
    result = json.loads(r.read())
    draft = result.get("draft", {})
    print("ok:", result.get("ok"))
    print("draft_id:", draft.get("draft_id"))
    print("amount:", draft.get("amount"))
    print("debit:", draft.get("debit_account"))
    print("credit:", draft.get("credit_account"))
    print("status:", draft.get("status"))
    print("partner:", draft.get("partner"))