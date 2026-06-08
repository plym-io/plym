CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.set_published_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'published' AND (OLD.status IS DISTINCT FROM 'published') THEN
        NEW.published_at = COALESCE(NEW.published_at, NOW());
    END IF;
    IF NEW.status <> 'published' THEN
        NEW.published_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pl_posts_touch ON public.pl_posts;
CREATE TRIGGER trg_pl_posts_touch
    BEFORE UPDATE ON public.pl_posts
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS trg_pl_posts_published ON public.pl_posts;
CREATE TRIGGER trg_pl_posts_published
    BEFORE INSERT OR UPDATE OF status ON public.pl_posts
    FOR EACH ROW EXECUTE FUNCTION public.set_published_at();

DROP TRIGGER IF EXISTS trg_pl_users_touch ON public.pl_users;
CREATE TRIGGER trg_pl_users_touch
    BEFORE UPDATE ON public.pl_users
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS trg_auth_users_touch ON auth.users;
CREATE TRIGGER trg_auth_users_touch
    BEFORE UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
