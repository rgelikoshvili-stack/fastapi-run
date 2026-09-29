# Email poller async event-loop fix

## Current bug

The email poller previously submitted the entire asynchronous
`collect_tenant_inbox()` coroutine to a worker thread and invoked it there with
`asyncio.run()`. That created a new event loop for every tenant poll.

`collect_tenant_inbox()` performs asynchronous database work through the
application's shared asyncpg pool. asyncpg connections and futures belong to
the event loop that created them, so using the pool from the temporary worker
loop could produce `ConnectionDoesNotExistError`, SSL protocol failures, and
unretrieved future exceptions.

The outer `wait_for(run_in_executor(...), timeout=20)` also cancelled only the
executor future. It could not stop the worker thread or the nested event loop,
allowing timed-out work to continue in the background.

## Fix

The poller now awaits `collect_tenant_inbox(tenant_id)` directly on the
application event loop with a 20-second per-tenant timeout. Timeout and failure
handling remain isolated per tenant, so one failed mailbox does not stop later
tenants.

The collector still uses synchronous `imaplib`, so only the blocking IMAP
operations are sent to `asyncio.to_thread()`:

- connect, login, and inbox selection;
- unseen-message search;
- message fetch;
- marking a message as seen; and
- logout.

Credential lookup, duplicate checks, document persistence, AI processing, and
all other database calls remain awaited on the application event loop. No
asyncpg operation runs in an IMAP worker thread.

## Out of scope

This change does not rotate or replace the Gmail app password, modify
`SMTP_PASS`, change production environment variables, call live integrations,
or repair historical posted-ledger data. Gmail credential rotation and Secret
Manager migration remain a separate operational task.
