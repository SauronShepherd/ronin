CREATE TABLE IF NOT EXISTS public.ui_page_accounts (
    id integer PRIMARY KEY,
    email text NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS public.ui_page_orders (
    id integer PRIMARY KEY,
    account_id integer NOT NULL,
    total numeric(10, 2) NOT NULL
);

INSERT INTO public.ui_page_accounts (id, email, updated_at)
VALUES (1, 'a@example.test', '2026-01-01T00:00:00Z')
ON CONFLICT (id) DO UPDATE
SET email = EXCLUDED.email, updated_at = EXCLUDED.updated_at;

INSERT INTO public.ui_page_orders (id, account_id, total)
VALUES (101, 1, 12.50)
ON CONFLICT (id) DO UPDATE SET account_id = EXCLUDED.account_id, total = EXCLUDED.total;
