-- Chat175: READ-ONLY finance/auth tenant-isolation catalog evidence template.
-- PREPARED ONLY. Do not run against Production without owner-approved viewer
-- permissions, verified database identity and a read-only session.
-- No customer rows, PII, credentials, DDL, GRANT, DELETE or UPDATE.
BEGIN TRANSACTION READ ONLY;

SELECT current_database() AS database_name, current_schema() AS schema_name,
       current_user AS inspected_role, current_setting('server_version') AS pg_version,
       current_setting('app.current_tenant_id', true) AS tenant_context,
       has_schema_privilege(current_user,current_schema(),'CREATE') AS can_create;

SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
FROM pg_roles WHERE rolname = current_user;

SELECT n.nspname AS schema_name, c.relname AS table_name,
       pg_get_userbyid(c.relowner) AS table_owner,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
       has_table_privilege(current_user, c.oid, 'SELECT') AS can_select,
       has_table_privilege(current_user, c.oid, 'INSERT') AS can_insert,
       has_table_privilege(current_user, c.oid, 'UPDATE') AS can_update,
       has_table_privilege(current_user, c.oid, 'DELETE') AS can_delete
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema()
  AND c.relkind IN ('r', 'p')
  AND c.relname IN (
      'tenants','users','pipeline_runs','audit_log',
      'journal_drafts','journal_entries','bank_transactions',
      'oauth_login_states','password_reset_tokens'
  )
ORDER BY c.relname;

SELECT schemaname, tablename, policyname, permissive, roles, cmd,
       qual, with_check
FROM pg_policies
WHERE schemaname = current_schema()
  AND tablename IN (
      'tenants','users','pipeline_runs','audit_log',
      'journal_drafts','journal_entries','bank_transactions',
      'oauth_login_states','password_reset_tokens'
  )
ORDER BY tablename, policyname;

SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name IN ('tenants','pipeline_runs','audit_log')
  AND column_name IN (
      'tenant_id','signature_b64','stamp_b64','run_id','filename',
      'state','resource','resource_id','created_at'
  )
ORDER BY table_name, ordinal_position;

ROLLBACK;
