-- Cappadocia balloon launch sites + nearby airports.
-- Coordinates verified against OpenStreetMap & official airport publications.

INSERT INTO locations (slug, name, kind, icao, latitude, longitude, elevation_m, notes) VALUES
  -- Launch sites (where balloons actually take off)
  ('goreme',     'Göreme',                  'launch_site', NULL, 38.6431, 34.8289, 1100, 'Main launch valley; iconic photos taken here.'),
  ('cavusin',    'Çavuşin',                 'launch_site', NULL, 38.6620, 34.8420, 1110, 'Small village just N of Göreme; backup launch field.'),
  ('uchisar',    'Uçhisar',                 'launch_site', NULL, 38.6310, 34.8060, 1230, 'Higher elevation, panoramic views.'),
  ('ortahisar',  'Ortahisar',               'launch_site', NULL, 38.6200, 34.8650, 1180, 'East of Göreme, occasional launch site.'),
  ('urgup',      'Ürgüp',                   'launch_site', NULL, 38.6310, 34.9120, 1050, 'Eastern launch zone; used when winds favour east-to-west drift.'),
  ('avanos',     'Avanos',                  'launch_site', NULL, 38.7160, 34.8470, 920,  'Northern launch zone along Kızılırmak river.'),
  -- Aviation reference points (METAR/TAF source)
  ('ltaz',       'Kapadokya Airport',       'airport',     'LTAZ', 38.7710, 34.5210, 944,  'Nearest airport to Göreme; primary METAR source.'),
  ('ltau',       'Kayseri Erkilet',         'airport',     'LTAU', 38.7700, 35.4950, 1053, 'Larger airport ~70km E; richer aviation data.')
ON CONFLICT (slug) DO UPDATE SET
  name        = EXCLUDED.name,
  kind        = EXCLUDED.kind,
  icao        = EXCLUDED.icao,
  latitude    = EXCLUDED.latitude,
  longitude   = EXCLUDED.longitude,
  elevation_m = EXCLUDED.elevation_m,
  notes       = EXCLUDED.notes;
