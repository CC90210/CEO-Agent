SELECT table_schema || '.' || table_name AS full_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'storage', 'auth', 'realtime', 'graphql', 'graphql_public', 'pgsodium', 'pgsodium_masks', 'extensions', 'net', 'supabase_functions', 'vault', '_realtime')
ORDER BY 1;
