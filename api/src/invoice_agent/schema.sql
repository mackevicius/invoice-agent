CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS demo_companies (
    id UUID PRIMARY KEY,
    session_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (currency = 'EUR')
);

CREATE INDEX IF NOT EXISTS demo_companies_expiry ON demo_companies(expires_at);

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
    description TEXT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    embedding vector(1536),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, purchase_order_id)
        REFERENCES purchase_orders(company_id, id)
);

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
    supplier_id UUID NOT NULL,
    supplier_name TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    total NUMERIC(14, 2) NOT NULL CHECK (total >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (currency = 'EUR'),
    status TEXT NOT NULL CHECK (
        status IN ('Processing', 'In Review', 'Auto-Approved', 'Approved', 'Rejected')
    ),
    issued_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, supplier_id) REFERENCES suppliers(company_id, id)
);

CREATE INDEX IF NOT EXISTS invoices_company_created
    ON invoices(company_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES demo_companies(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    FOREIGN KEY (company_id, invoice_id) REFERENCES invoices(company_id, id)
);
