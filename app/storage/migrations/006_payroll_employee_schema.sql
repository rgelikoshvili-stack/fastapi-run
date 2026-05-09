-- Bridge Hub Task 10D-C
-- Payroll and employee portal schema canonical additive migration.
--
-- This migration mirrors the existing runtime payroll/employee bootstrap in
-- app/api/services/payroll_service.py and app/api/routes_employee_portal.py.
-- It is intentionally additive only and does not remove runtime compatibility
-- wrappers.

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    employee_id VARCHAR(50),
    name VARCHAR(255) NOT NULL,
    personal_number VARCHAR(20),
    email VARCHAR(255),
    position VARCHAR(255),
    department VARCHAR(255),
    gross_salary NUMERIC(12,2) DEFAULT 0,
    hire_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    portal_token VARCHAR(64),
    portal_token_expires TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, personal_number)
);

CREATE TABLE IF NOT EXISTS pension_transfers (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    period VARCHAR(7) NOT NULL,
    employee_count INT DEFAULT 0,
    total_employee_pension NUMERIC(12,2) DEFAULT 0,
    total_employer_pension NUMERIC(12,2) DEFAULT 0,
    total_amount NUMERIC(12,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    transfer_reference VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    period VARCHAR(7) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    employee_count INT DEFAULT 0,
    total_gross NUMERIC(12,2) DEFAULT 0,
    total_pit NUMERIC(12,2) DEFAULT 0,
    total_employee_pension NUMERIC(12,2) DEFAULT 0,
    total_employer_pension NUMERIC(12,2) DEFAULT 0,
    total_net NUMERIC(12,2) DEFAULT 0,
    total_employer_cost NUMERIC(12,2) DEFAULT 0,
    draft_ids JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_run_lines (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    run_id INT NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    employee_db_id INT,
    employee_id VARCHAR(50),
    employee_name VARCHAR(255) NOT NULL,
    personal_number VARCHAR(20),
    gross_salary NUMERIC(12,2) NOT NULL,
    pit_20pct NUMERIC(12,2) NOT NULL,
    employee_pension_2pct NUMERIC(12,2) NOT NULL,
    employer_pension_2pct NUMERIC(12,2) NOT NULL,
    net_salary NUMERIC(12,2) NOT NULL,
    total_employer_cost NUMERIC(12,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_tenant_status
    ON employees(tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_payroll_runs_tenant_period_status
    ON payroll_runs(tenant_id, period, status);

CREATE INDEX IF NOT EXISTS idx_payroll_run_lines_tenant_run
    ON payroll_run_lines(tenant_id, run_id);

CREATE INDEX IF NOT EXISTS idx_pension_transfers_tenant_period_status
    ON pension_transfers(tenant_id, period, status);
