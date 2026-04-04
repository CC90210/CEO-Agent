---
name: supabase-patterns
description: Use this skill whenever the user asks about Supabase, database design, postgres, creating tables, writing SQL, RLS policies, performing database CRUD, or backend data patterns.
triggers: [Supabase, SQL, migration, RLS, schema, database, postgres, CRUD]
tier: standard
dependencies: []
---

# Supabase Patterns — Skill Reference

## Database Design Standards

### Every Table Must Have
- `id` — UUID, primary key, default `gen_random_uuid()`
- `created_at` — timestamptz, default `now()`
- `updated_at` — timestamptz, auto-updated via trigger
- Row Level Security (RLS) enabled — NO EXCEPTIONS

### Common Patterns

#### Multi-Tenant Isolation
```sql
-- Every table has an organization_id
ALTER TABLE properties ADD COLUMN organization_id UUID REFERENCES organizations(id);

-- RLS policy: users only see their org's data
CREATE POLICY "Users see own org data" ON properties
  FOR ALL USING (organization_id = (SELECT organization_id FROM users WHERE id = auth.uid()));
```

#### Soft Deletes
```sql
ALTER TABLE table_name ADD COLUMN deleted_at timestamptz DEFAULT NULL;
-- Filter in queries: WHERE deleted_at IS NULL
```

#### Status Workflow
```sql
-- Use enums for status columns
CREATE TYPE application_status AS ENUM ('submitted', 'screening', 'approved', 'denied', 'withdrawn');
ALTER TABLE applications ADD COLUMN status application_status DEFAULT 'submitted';
```

### Auth Patterns
- Use Supabase Auth for all user management
- Store additional user data in a `profiles` table linked to `auth.users`
- Use RLS policies that reference `auth.uid()`
- Never store passwords or auth tokens in custom tables

### Edge Functions
- Use for server-side logic that needs secrets
- Keep functions focused — one function per task
- Always validate input
- Return consistent JSON response format
- Handle CORS properly

### Real-time Subscriptions
- Use for live dashboards and real-time updates
- Subscribe to specific table changes with filters
- Always handle subscription cleanup on component unmount
- Consider performance — don't subscribe to high-frequency tables without filters

## Query Patterns

### Efficient Pagination
```typescript
const { data, count } = await supabase
  .from('table')
  .select('*', { count: 'exact' })
  .range(offset, offset + limit - 1)
  .order('created_at', { ascending: false });
```

### Joining Related Data
```typescript
const { data } = await supabase
  .from('buildings')
  .select(`*, units(*), areas(name)`)
  .eq('organization_id', orgId);
```

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
