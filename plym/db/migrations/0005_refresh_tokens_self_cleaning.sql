DELETE FROM auth.refresh_tokens
WHERE expires_at < NOW() OR revoked = TRUE;

ALTER TABLE auth.refresh_tokens DROP COLUMN revoked;

CREATE OR REPLACE FUNCTION auth.purge_expired_refresh_tokens()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM auth.refresh_tokens WHERE expires_at < NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_purge_expired_refresh_tokens ON auth.refresh_tokens;
CREATE TRIGGER trg_purge_expired_refresh_tokens
    BEFORE INSERT ON auth.refresh_tokens
    FOR EACH STATEMENT
    EXECUTE FUNCTION auth.purge_expired_refresh_tokens();
