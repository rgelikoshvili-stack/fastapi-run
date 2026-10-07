-- NEXT-04A11: READ-ONLY production runtime-role verification pack.
-- An authorized operator must connect exactly as the Cloud Run runtime identity.
-- Do not run as an administrator, proxy owner, or migration role.
\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;

-- Q1: session identity and effective role attributes.
SELECT current_user, session_user, r.rolname, r.rolsuper, r.rolbypassrls,
       r.rolcreaterole, r.rolcreatedb, r.rolcanlogin
FROM pg_roles AS r
WHERE r.rolname = current_user;

-- Q2: direct and inherited memberships for current_user.
WITH RECURSIVE memberships(member_oid, role_oid, depth, path) AS (
    SELECT m.member, m.roleid, 1, ARRAY[m.member, m.roleid]
    FROM pg_auth_members AS m
    WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = current_user)
  UNION ALL
    SELECT m.member, m.roleid, x.depth + 1, x.path || m.roleid
    FROM memberships AS x
    JOIN pg_auth_members AS m ON m.member = x.role_oid
    WHERE NOT m.roleid = ANY(x.path)
)
SELECT pg_get_userbyid(member_oid) AS member_name,
       pg_get_userbyid(role_oid) AS granted_role,
       depth
FROM memberships
ORDER BY depth, granted_role;

-- Shared protected-table relation used by the remaining checks.
WITH protected(name) AS (VALUES
 ('counterparties'), ('processed_documents'), ('journal_drafts'),
 ('waybills'), ('tax_invoices'), ('commercial_invoices'),
 ('triangle_matches'), ('document_corrections'), ('outgoing_invoices')
)
SELECT p.name AS table_name,
       n.nspname AS schema_name,
       c.oid::regclass AS qualified_table,
       pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity,
       c.relforcerowsecurity,
       (c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)) AS runtime_is_owner,
       has_table_privilege(current_user, c.oid, 'SELECT') AS can_select,
       has_table_privilege(current_user, c.oid, 'INSERT') AS can_insert,
       has_table_privilege(current_user, c.oid, 'UPDATE') AS can_update,
       has_table_privilege(current_user, c.oid, 'DELETE') AS can_delete,
       has_table_privilege(current_user, c.oid, 'TRUNCATE') AS can_truncate,
       has_table_privilege(current_user, c.oid, 'TRIGGER') AS can_trigger
FROM protected AS p
LEFT JOIN pg_class AS c ON c.relname = p.name AND c.relkind IN ('r','p')
LEFT JOIN pg_namespace AS n ON n.oid = c.relnamespace
ORDER BY p.name;

-- Q4: policies. Expected: exactly one tenant_fail_closed_<table> ALL policy
-- per protected table, with restrictive tenant expressions shown for review.
WITH protected(name) AS (VALUES
 ('counterparties'), ('processed_documents'), ('journal_drafts'),
 ('waybills'), ('tax_invoices'), ('commercial_invoices'),
 ('triangle_matches'), ('document_corrections'), ('outgoing_invoices')
)
SELECT p.name AS table_name, pol.schemaname, pol.policyname, pol.permissive,
       pol.roles, pol.cmd, pol.qual, pol.with_check
FROM protected AS p
LEFT JOIN pg_policies AS pol ON pol.tablename = p.name
ORDER BY p.name, pol.policyname;

-- Q5: schema ownership and CREATE privilege. The runtime role should own no
-- protected schema and should not have CREATE on it.
SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS owner,
       (n.nspowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)) AS runtime_is_schema_owner,
       has_schema_privilege(current_user, n.oid, 'USAGE') AS can_use_schema,
       has_schema_privilege(current_user, n.oid, 'CREATE') AS can_create_in_schema
FROM pg_namespace AS n
WHERE n.oid IN (
  SELECT DISTINCT c.relnamespace FROM pg_class AS c
  WHERE c.relname = ANY(ARRAY[
    'counterparties','processed_documents','journal_drafts','waybills',
    'tax_invoices','commercial_invoices','triangle_matches',
    'document_corrections','outgoing_invoices'
  ])
);

-- Q6: derived DDL capability. PostgreSQL has no grantable ALTER TABLE or
-- CREATE/DROP POLICY table privilege: table ownership (or superuser) controls
-- those commands. All three derived flags must be false for the runtime role.
WITH role_state AS (
  SELECT oid, rolsuper FROM pg_roles WHERE rolname = current_user
), protected AS (VALUES
 ('counterparties'), ('processed_documents'), ('journal_drafts'),
 ('waybills'), ('tax_invoices'), ('commercial_invoices'),
 ('triangle_matches'), ('document_corrections'), ('outgoing_invoices')
), owned AS (
  SELECT count(*) FILTER (WHERE c.relowner = r.oid) AS owned_count,
         bool_or(r.rolsuper) AS is_super
  FROM protected p(name)
  JOIN pg_class c ON c.relname = p.name AND c.relkind IN ('r','p')
  CROSS JOIN role_state r
)
SELECT owned_count,
       (is_super OR owned_count > 0) AS can_alter_protected_table,
       (is_super OR owned_count > 0) AS can_create_or_drop_policy,
       (is_super OR owned_count > 0) AS possesses_protected_table_migration_ddl;

ROLLBACK;
