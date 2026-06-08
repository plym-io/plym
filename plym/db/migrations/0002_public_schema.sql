CREATE SCHEMA IF NOT EXISTS public;

CREATE TABLE IF NOT EXISTS public.pl_users (
    id           BIGINT PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    bio          TEXT,
    avatar_url   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.pl_posts (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    author_id     BIGINT NOT NULL REFERENCES public.pl_users(id) ON DELETE RESTRICT,
    status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    reading_time  INTEGER NOT NULL DEFAULT 0,
    content_md    TEXT NOT NULL DEFAULT '',
    rendered_path TEXT,
    excerpt       TEXT,
    cover_image   TEXT,
    published_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pl_posts_status_published ON public.pl_posts(status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pl_posts_author ON public.pl_posts(author_id);

CREATE TABLE IF NOT EXISTS public.pl_tags (
    id     BIGSERIAL PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    slug   TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS public.pl_post_tags (
    post_id BIGINT NOT NULL REFERENCES public.pl_posts(id) ON DELETE CASCADE,
    tag_id  BIGINT NOT NULL REFERENCES public.pl_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

CREATE TABLE IF NOT EXISTS public.pl_logs (
    id         BIGSERIAL PRIMARY KEY,
    event      TEXT NOT NULL,
    actor_id   BIGINT REFERENCES auth.users(id) ON DELETE SET NULL,
    target     TEXT,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pl_logs_event ON public.pl_logs(event);
CREATE INDEX IF NOT EXISTS idx_pl_logs_actor ON public.pl_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_pl_logs_created ON public.pl_logs(created_at DESC);
