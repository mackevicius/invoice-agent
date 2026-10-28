CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS demo_companies (
    id UUID PRIMARY KEY,
    session_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (currency = 'EUR')
);

ALTER TABLE demo_companies ADD COLUMN IF NOT EXISTS visitor_id UUID;
UPDATE demo_companies SET visitor_id = id WHERE visitor_id IS NULL;
ALTER TABLE demo_companies ALTER COLUMN visitor_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS demo_companies_expiry ON demo_companies(expires_at);

CREATE TABLE IF NOT EXISTS daily_ai_usage (
    usage_date DATE NOT NULL,
    visitor_id UUID NOT NULL,
    calls INTEGER NOT NULL CHECK (calls > 0),
    PRIMARY KEY (usage_date, visitor_id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE (company_id, id),
    UNIQUE (company_id, name)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    supplier_id UUID NOT NULL,
    number TEXT NOT NULL,
    UNIQUE (company_id, id),
    UNIQUE (company_id, number),
    FOREIGN KEY (company_id, supplier_id) REFERENCES suppliers(company_id, id)
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    purchase_order_id UUID NOT NULL,
    item_code TEXT,
    description TEXT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    embedding vector(1536),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, purchase_order_id)
        REFERENCES purchase_orders(company_id, id)
);

ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS item_code TEXT;

CREATE TABLE IF NOT EXISTS goods_receipts (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    purchase_order_id UUID NOT NULL,
    number TEXT NOT NULL,
    UNIQUE (company_id, id),
    UNIQUE (company_id, number),
    FOREIGN KEY (company_id, purchase_order_id)
        REFERENCES purchase_orders(company_id, id)
);

CREATE TABLE IF NOT EXISTS goods_receipt_lines (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    goods_receipt_id UUID NOT NULL,
    purchase_order_line_id UUID NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (company_id, goods_receipt_id)
        REFERENCES goods_receipts(company_id, id),
    FOREIGN KEY (company_id, purchase_order_line_id)
        REFERENCES purchase_order_lines(company_id, id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    supplier_id UUID,
    supplier_name TEXT,
    invoice_number TEXT,
    total NUMERIC(14, 2) CHECK (total >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (currency ~ '^[A-Z]{3}$'),
    status TEXT NOT NULL CHECK (
        status IN ('Processing', 'In Review', 'Auto-Approved', 'Approved', 'Rejected')
    ),
    issued_on DATE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, supplier_id) REFERENCES suppliers(company_id, id)
);

ALTER TABLE invoices
    ALTER COLUMN supplier_id DROP NOT NULL,
    ALTER COLUMN supplier_name DROP NOT NULL,
    ALTER COLUMN invoice_number DROP NOT NULL,
    ALTER COLUMN total DROP NOT NULL,
    ALTER COLUMN issued_on DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS file_name TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS file_content BYTEA,
    ADD COLUMN IF NOT EXISTS read_fields JSONB,
    ADD COLUMN IF NOT EXISTS reasons JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS comparison JSONB NOT NULL DEFAULT '[]';

ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_currency_check;
ALTER TABLE invoices ADD CONSTRAINT invoices_currency_check
    CHECK (currency ~ '^[A-Z]{3}$');

CREATE INDEX IF NOT EXISTS invoices_company_created
    ON invoices(company_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS invoice_steps (
    company_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (
        status IN ('Pending', 'Running', 'Completed', 'Failed', 'Skipped')
    ),
    inputs JSONB NOT NULL,
    outputs JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (company_id, invoice_id, name),
    FOREIGN KEY (company_id, invoice_id)
        REFERENCES invoices(company_id, id) ON DELETE CASCADE
);

ALTER TABLE invoice_steps DROP CONSTRAINT IF EXISTS invoice_steps_status_check;
ALTER TABLE invoice_steps ADD CONSTRAINT invoice_steps_status_check
    CHECK (status IN ('Pending', 'Running', 'Completed', 'Failed', 'Skipped'));

CREATE TABLE IF NOT EXISTS invoice_lines (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL,
    item_code TEXT,
    description TEXT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    FOREIGN KEY (company_id, invoice_id) REFERENCES invoices(company_id, id)
);

ALTER TABLE invoice_lines ADD COLUMN IF NOT EXISTS item_code TEXT;
