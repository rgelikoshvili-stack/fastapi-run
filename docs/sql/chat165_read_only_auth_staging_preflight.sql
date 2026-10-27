-- Chat165 — READ ONLY staging schema/permission preflight.
-- Do not execute automatically or against live Production. Runs no user-data SELECT.
-- Use only on an explicitly approved isolated staging PostgreSQL database.
BEGIN READ ONLY;

SELECT current_database() AS db_name,
       current_schema() AS schema_name,
       current_setting('server_version_num') AS pg_version_num,
       current_user AS db_role,
       (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) AS role_bypasses_rls,
       (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS role_is_superuser;

SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name IN ('users', 'oauth_login_states')
  AND column_name IN (
      'id', 'email', 'role', 'tenant_id', 'is_active', 'password_hash',
      'state_hash', 'provider', 'expires_at', 'created_at'
  )
ORDER BY table_name, ordinal_position;

SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_force_owner,
       pg_get_userbyid(c.relowner) AS table_owner,
       has_table_privilege(c.oid, 'SELECT') AS can_select
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema()
  AND c.relkind IN ('r', 'p')
  AND c.relname IN ('users', 'oauth_login_states')
ORDER BY c.relname;

SELECT t.relname AS table_name, i.relname AS index_name,
       x.indisprimary AS is_primary, x.indisunique AS is_unique
FROM pg_index x
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = current_schema()
  AND t.relname IN ('users', 'oauth_login_states')
ORDER BY t.relname, i.relname;

SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = current_schema()
  AND tablename IN ('users', 'oauth_login_states')
ORDER BY tablename, policyname;

COMMIT;
