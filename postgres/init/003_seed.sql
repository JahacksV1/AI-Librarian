-- Test user
INSERT INTO users (id, name, email, timezone)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Test User',
  'test@aijah.local',
  'UTC'
) ON CONFLICT DO NOTHING;

-- Test device
INSERT INTO devices (id, user_id, name, device_type, hostname)
VALUES (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'Dev Machine',
  'WINDOWS_PC',
  'aijah-dev'
) ON CONFLICT DO NOTHING;
