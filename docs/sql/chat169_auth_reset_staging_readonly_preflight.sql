-- Chat169: READ-ONLY schema/role preflight for a separately approved
-- ISOLATED STAGING PostgreSQL database. Never executes DDL or writes.
-- Run separately as the intended staging RUNTIME role; inspect results offline.
-- Do not connect this script to Production without a specific approved review.
BEGIN TRANSACTION READ ONLY;

SELECT current_database() AS database_name,
       current_schema() AS schema_name,
       current_user AS runtime_role,
       current_setting('server_version') AS pg_version,
       current_setting('app.current_tenant_id', true) AS transaction_tenant,
       has_schema_privilege(current_user, current_schema(), 'CREATE')
           AS runtime_can_create_schema_objects;

SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
FROM pg_roles
WHERE rolname = current_user;

SELECT n.nspname AS table_schema, c.relname AS table_name,
       pg_get_userbyid(c.relowner) AS table_owner,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced,
       has_table_privilege(current_user, c.oid, 'SELECT') AS runtime_can_select,
       has_table_privilege(current_user, c.oid, 'INSERT') AS runtime_can_insert,
       has_table_privilege(current_user, c.oid, 'UPDATE') AS runtime_can_update,
       has_table_privilege(current_user, c.oid, 'DELETE') AS runtime_can_delete
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema()
  AND c.relkind IN ('r', 'p')
  AND c.relname IN ('users', 'password_reset_tokens', 'oauth_login_states')
ORDER BY c.relname;

SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND (
       (table_name = 'users' AND column_name IN
           ('id', 'tenant_id', 'is_active', 'auth_version'))
    OR (table_name = 'password_reset_tokens' AND column_name IN
           ('token', 'email', 'tenant_id', 'expires_at', 'used'))
  )
ORDER BY table_name, ordinal_position;

SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = current_schema()
  AND tablename IN ('users', 'password_reset_tokens')
ORDER BY tablename, policyname;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename IN ('users', 'password_reset_tokens')
ORDER BY tablename, indexname;

ROLLBACK;
