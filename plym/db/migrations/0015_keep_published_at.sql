CREATE OR REPLACE FUNCTION public.set_published_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'published' AND (OLD.status IS DISTINCT FROM 'published') THEN
        NEW.published_at = COALESCE(NEW.published_at, OLD.published_at, NOW());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
