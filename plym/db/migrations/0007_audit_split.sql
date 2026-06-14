CREATE TABLE IF NOT EXISTS public.pl_audit (
    id         BIGSERIAL PRIMARY KEY,
    event      TEXT NOT NULL,
    actor_id   BIGINT REFERENCES auth.users(id) ON DELETE SET NULL,
    target     TEXT,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.pl_audit (event, actor_id, target, payload, created_at)
SELECT event, actor_id, target, payload, created_at
FROM public.pl_logs
WHERE audit = TRUE;

CREATE INDEX IF NOT EXISTS idx_pl_audit_event ON public.pl_audit(event);
CREATE INDEX IF NOT EXISTS idx_pl_audit_actor ON public.pl_audit(actor_id);
CREATE INDEX IF NOT EXISTS idx_pl_audit_created ON public.pl_audit(created_at DESC);

DROP TABLE IF EXISTS public.pl_logs;
