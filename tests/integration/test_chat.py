# -*- coding: utf-8 -*-
import urllib.request
import json

boundary = "simpleboundary"
message = "TBC test chat"

body = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"message\"\r\n\r\n"
    f"{message}\r\n"
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"session_id\"\r\n\r\n"
    f"test123\r\n"
    f"--{boundary}--\r\n"
).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/chat/message",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)

try:
    with urllib.request.urlopen(req) as r:
        res = json.loads(r.read())
        print("ok:", res.get("ok"))
        reply = res.get("data", {}).get("reply", "")
        print("reply:", str(reply)[:200])
except Exception as e:
    print("ERROR:", e)
