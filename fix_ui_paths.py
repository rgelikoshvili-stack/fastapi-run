with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()

# pending queue
content = content.replace(
    "'/approvals/pending','/transactions/pending','/approvals?status=pending'",
    "'/approval/queue','/approvals/pending','/transactions/pending'"
)

# approved
content = content.replace(
    "api('/approvals/approved')",
    "api('/approval/queue?status=approved')"
)

# rejected  
content = content.replace(
    "api('/approvals/rejected')",
    "api('/approval/queue?status=rejected')"
)

# approve action
content = content.replace(
    "`/approvals/${id}/approve`,`/journal-drafts/${id}/approve`,`/transactions/${id}/approve`",
    "`/approval/approve/${id}`,`/approvals/${id}/approve`,`/journal-drafts/${id}/approve`"
)

# reject action
content = content.replace(
    "`/approvals/${id}/reject`,`/journal-drafts/${id}/reject`,`/transactions/${id}/reject`",
    "`/approval/reject/${id}`,`/approvals/${id}/reject`,`/journal-drafts/${id}/reject`"
)

with open("static/approval.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
