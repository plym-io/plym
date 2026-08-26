CREATE TABLE IF NOT EXISTS public.pl_faqs (
    id         BIGSERIAL PRIMARY KEY,
    data       JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.pl_post_faqs (
    post_id  BIGINT NOT NULL REFERENCES public.pl_posts(id) ON DELETE CASCADE,
    faq_id   BIGINT NOT NULL REFERENCES public.pl_faqs(id) ON DELETE CASCADE,
    position INT NOT NULL DEFAULT 0,
    PRIMARY KEY (post_id, faq_id)
);

CREATE INDEX IF NOT EXISTS idx_pl_post_faqs_post ON public.pl_post_faqs(post_id);

DROP TRIGGER IF EXISTS trg_pl_faqs_touch ON public.pl_faqs;
CREATE TRIGGER trg_pl_faqs_touch
    BEFORE UPDATE ON public.pl_faqs
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
