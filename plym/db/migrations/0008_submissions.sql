CREATE TABLE IF NOT EXISTS public.pl_submissions (
    id          BIGSERIAL PRIMARY KEY,
    payload     JSONB NOT NULL,
    user_agent  TEXT,
    client_addr INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pl_submissions_created ON public.pl_submissions(created_at DESC);
