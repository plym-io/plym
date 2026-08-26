CREATE TABLE IF NOT EXISTS public.pl_categories (
    id     BIGSERIAL PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    slug   TEXT NOT NULL UNIQUE,
    weight INT
);

ALTER TABLE public.pl_posts
    ADD COLUMN IF NOT EXISTS category_id BIGINT
    REFERENCES public.pl_categories(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_pl_posts_category ON public.pl_posts(category_id);

ALTER TABLE public.pl_tags DROP COLUMN IF EXISTS weight;
