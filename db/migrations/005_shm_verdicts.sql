-- Scraped go/no-go verdicts from the official Slot Hizmet Merkezi (SHM)
-- page run by Kapadokya Üniversitesi:
--   https://shmkapadokya.kapadokya.edu.tr/
--
-- Each row is one snapshot of one sector's verdict at fetch time. We store
-- every fetch (cheap) so we can later see when the duty officer flipped a
-- sector. The "current" verdict for a sector is the row with the most
-- recent issued_at.
--
-- This is the OFFICIAL call. Our forecast lives in forecast_hourly; SHM is
-- the ground truth we calibrate against.

CREATE TABLE IF NOT EXISTS shm_sector_verdict (
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sector      TEXT        NOT NULL,        -- 'A','B','C' (primary) or '2'..'5' (secondary)
    kind        TEXT        NOT NULL,        -- 'primary' | 'secondary'
    flag        TEXT        NOT NULL,        -- 'red' | 'yellow' | 'green'
    verdict     TEXT        NOT NULL,        -- 'UÇULMAZ' | 'UÇULUR' (raw Turkish)
    issued_at   TIMESTAMPTZ NOT NULL,        -- "GÜNCELLEME TARİHİ ve SAATİ" parsed in Europe/Istanbul
    valid_from  TIMESTAMPTZ NOT NULL,        -- start of the validity window
    valid_to    TIMESTAMPTZ NOT NULL,        -- end of the validity window
    PRIMARY KEY (sector, issued_at)
);

CREATE INDEX IF NOT EXISTS idx_shm_sector_verdict_sector_time
    ON shm_sector_verdict (sector, issued_at DESC);

-- Convenience view: latest row per sector.
CREATE OR REPLACE VIEW v_shm_latest AS
SELECT DISTINCT ON (sector)
    sector, kind, flag, verdict, issued_at, valid_from, valid_to, fetched_at
FROM shm_sector_verdict
ORDER BY sector, issued_at DESC, fetched_at DESC;

-- ---------------------------------------------------------------------------
-- Map each launch site to its containing SHM primary sector.
-- Cappadocia primary sectors (rough coverage from the SHM map):
--   A = North  (Avanos)
--   B = Central (Göreme, Çavuşin, Uçhisar, Ortahisar)
--   C = South  (Ürgüp)
-- ---------------------------------------------------------------------------
ALTER TABLE locations
    ADD COLUMN IF NOT EXISTS shm_sector TEXT;

UPDATE locations SET shm_sector = 'A' WHERE slug = 'avanos';
UPDATE locations SET shm_sector = 'B' WHERE slug IN ('goreme', 'cavusin', 'uchisar', 'ortahisar');
UPDATE locations SET shm_sector = 'C' WHERE slug = 'urgup';
