ALTER TABLE public.pl_posts RENAME COLUMN cover_image TO cover;
ALTER TABLE public.pl_posts RENAME COLUMN content_md TO content;

CREATE TABLE IF NOT EXISTS public.pl_media (
    id            BIGSERIAL PRIMARY KEY,
    filename      TEXT NOT NULL UNIQUE,
    original_name TEXT,
    mime_type     TEXT NOT NULL DEFAULT 'image/webp',
    size_bytes    INTEGER NOT NULL,
    width         INTEGER,
    height        INTEGER,
    url           TEXT NOT NULL,
    uploader_id   BIGINT REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pl_media_uploader ON public.pl_media(uploader_id);
CREATE INDEX IF NOT EXISTS idx_pl_media_created ON public.pl_media(created_at DESC);
