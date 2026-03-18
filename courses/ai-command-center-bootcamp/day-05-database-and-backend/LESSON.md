# Day 5: Database & Backend — Supabase

> **Level:** Integrator (Level 2)
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 4 complete
> **Goal:** Set up a real database, write SQL queries, connect it to your AI agent.

---

## Module 1: Why Databases? (15 min)

### When Files Aren't Enough

Files work for small projects. But when you need to:
- Store thousands of records
- Search data fast
- Have multiple users access the same data
- Keep data safe with backups
- Control who can see/edit what

You need a **database**.

### Types of Databases

| Type | Example | Best For |
|------|---------|----------|
| **Relational (SQL)** | PostgreSQL, MySQL | Structured data, business apps |
| **Document** | MongoDB, Firestore | Flexible schemas, rapid prototyping |
| **Key-Value** | Redis | Caching, sessions, fast lookups |
| **Vector** | Pinecone, pgvector | AI embeddings, similarity search |

**We're using PostgreSQL via Supabase** — the gold standard for business applications.

---

## Module 2: Supabase Setup (20 min)

### What Is Supabase?

Supabase = PostgreSQL database + authentication + file storage + real-time subscriptions + API auto-generation — all in one platform. Think "Firebase but open source."

### Create Your Project

1. Go to https://supabase.com
2. Sign up (GitHub login works)
3. Click "New Project"
4. Choose:
   - **Organization:** Your personal org
   - **Project name:** `ai-bootcamp`
   - **Database password:** Generate a strong one (SAVE THIS)
   - **Region:** Closest to you
5. Wait ~2 minutes for provisioning

### Dashboard Tour

| Section | Purpose |
|---------|---------|
| **Table Editor** | Visual spreadsheet-like interface for your data |
| **SQL Editor** | Write and run raw SQL queries |
| **Authentication** | Manage users and login methods |
| **Storage** | File uploads (images, PDFs, etc.) |
| **Edge Functions** | Serverless backend code |
| **Settings → API** | Your API URL and keys |

### Get Your Keys

Go to Settings → API:
- **Project URL:** `https://xxxxx.supabase.co` — your API endpoint
- **anon key:** Public key for client-side access (safe to expose)
- **service_role key:** Full admin access (NEVER expose this)

**Save these in your .env file:**
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

---

## Module 3: SQL Basics (30 min)

### The Four Operations (CRUD)

#### CREATE (Insert data)
```sql
INSERT INTO contacts (name, email, phone, city)
VALUES ('Jane Smith', 'jane@email.com', '555-1234', 'Toronto');
```

#### READ (Query data)
```sql
-- Get everything
SELECT * FROM contacts;

-- Get specific columns
SELECT name, email FROM contacts;

-- Filter with WHERE
SELECT * FROM contacts WHERE city = 'Toronto';

-- Sort results
SELECT * FROM contacts ORDER BY name ASC;

-- Limit results
SELECT * FROM contacts LIMIT 10;

-- Count records
SELECT COUNT(*) FROM contacts;
```

#### UPDATE (Modify data)
```sql
UPDATE contacts
SET phone = '555-9999'
WHERE email = 'jane@email.com';
```

#### DELETE (Remove data)
```sql
DELETE FROM contacts
WHERE email = 'jane@email.com';
```

### Common Patterns

```sql
-- Search (LIKE for partial matching)
SELECT * FROM contacts WHERE name LIKE '%Smith%';

-- Multiple conditions
SELECT * FROM contacts WHERE city = 'Toronto' AND is_active = true;

-- Aggregate functions
SELECT city, COUNT(*) as total FROM contacts GROUP BY city;

-- Join tables (combine related data)
SELECT contacts.name, orders.amount
FROM contacts
JOIN orders ON contacts.id = orders.contact_id;
```

---

## Module 4: Tables & Schema Design (25 min)

### Creating Tables

```sql
CREATE TABLE contacts (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    phone       TEXT,
    city        TEXT,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

**Column Types:**
| Type | Use For | Example |
|------|---------|---------|
| `TEXT` | Any text | Names, emails, descriptions |
| `INTEGER` | Whole numbers | Age, count, quantity |
| `NUMERIC` | Decimals | Price, percentage |
| `BOOLEAN` | True/False | is_active, is_paid |
| `UUID` | Unique identifiers | IDs (auto-generated) |
| `TIMESTAMPTZ` | Date + time | created_at, updated_at |
| `JSONB` | Flexible data | Settings, metadata |

**Constraints:**
| Constraint | Meaning |
|-----------|---------|
| `PRIMARY KEY` | Unique identifier for each row |
| `NOT NULL` | Must have a value |
| `UNIQUE` | No duplicates allowed |
| `DEFAULT` | Auto-fill if not provided |
| `REFERENCES` | Links to another table (foreign key) |

### Relationships

**One-to-Many:** One customer has many orders
```sql
CREATE TABLE customers (
    id    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE orders (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id  UUID REFERENCES customers(id),
    amount       NUMERIC NOT NULL,
    status       TEXT DEFAULT 'pending',
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

### Design Tips
1. **Every table needs an `id`** (use UUID)
2. **Add `created_at` and `updated_at`** to every table
3. **Use `NOT NULL`** for required fields
4. **Use `UNIQUE`** for emails, usernames, etc.
5. **Name tables as plural nouns** (customers, orders, products)

---

## Module 5: Row Level Security (RLS) (20 min)

### Why RLS?

Without RLS, anyone with your anon key can read/write everything. RLS adds rules:
- Users can only see their own data
- Admins can see everything
- Public data is readable by all, writable by none

### Enable RLS

```sql
-- Enable RLS on a table
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;

-- Policy: anyone can read
CREATE POLICY "Public read" ON contacts
    FOR SELECT USING (true);

-- Policy: only authenticated users can insert
CREATE POLICY "Auth insert" ON contacts
    FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

-- Policy: users can only update their own rows
CREATE POLICY "Own update" ON contacts
    FOR UPDATE USING (auth.uid() = user_id);
```

### Key Rule
**Always enable RLS on every table.** A table without RLS is a security vulnerability.

---

## Module 6: Supabase + Claude Code (20 min)

### Via MCP

If you have the Supabase MCP configured, Claude Code can query your database directly:

```
List all tables in my Supabase project
```

```
Run this SQL: SELECT * FROM contacts WHERE city = 'Toronto'
```

### Via Python SDK

```bash
pip install supabase
```

```python
from supabase import create_client
import os

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_ANON_KEY")
supabase = create_client(url, key)

# Read
result = supabase.table("contacts").select("*").execute()
print(result.data)

# Insert
result = supabase.table("contacts").insert({
    "name": "John Doe",
    "email": "john@example.com",
    "city": "Collingwood"
}).execute()

# Update
result = supabase.table("contacts").update({
    "phone": "555-1234"
}).eq("email", "john@example.com").execute()

# Delete
result = supabase.table("contacts").delete().eq(
    "email", "john@example.com"
).execute()
```

---

## Module 7: Real-Time Features (15 min)

### What Is Real-Time?

Normal databases: You ask for data, you get data.
Real-time databases: Data **pushes** to you when it changes.

**Use cases:**
- Live dashboard updates
- Chat applications
- Notification systems
- Collaborative editing

### Enable Real-Time in Supabase

1. Go to Database → Replication
2. Enable replication on the table you want to watch
3. Subscribe in your code:

```javascript
// JavaScript example
const channel = supabase
  .channel('contacts-changes')
  .on('postgres_changes',
    { event: '*', schema: 'public', table: 'contacts' },
    (payload) => {
      console.log('Change detected:', payload)
    }
  )
  .subscribe()
```

---

## Exercise: Build a Contacts Database

**Step 1:** In your Supabase SQL Editor, create the table:
```sql
CREATE TABLE contacts (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    phone       TEXT,
    city        TEXT,
    notes       TEXT,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for now" ON contacts
    FOR ALL USING (true) WITH CHECK (true);
```

**Step 2:** Insert test data:
```sql
INSERT INTO contacts (name, email, city) VALUES
    ('Alice Johnson', 'alice@email.com', 'Toronto'),
    ('Bob Smith', 'bob@email.com', 'Collingwood'),
    ('Carol Williams', 'carol@email.com', 'Vancouver');
```

**Step 3:** Build a Python CLI tool:
```bash
cd ~/ai-bootcamp/day-05
claude
```

Ask Claude Code:
```
Build a Python CLI tool called contacts_tool.py that connects to my Supabase database.
My SUPABASE_URL and SUPABASE_ANON_KEY are in my .env file.

Commands:
- python contacts_tool.py list              → Show all contacts
- python contacts_tool.py add "Name" "email" "city"  → Add contact
- python contacts_tool.py search "Toronto"  → Search by city
- python contacts_tool.py delete "email"    → Delete by email
- Support --json flag on all commands
```

**Step 4:** Test it:
```bash
python contacts_tool.py list
python contacts_tool.py add "Dave Chen" "dave@email.com" "Montreal"
python contacts_tool.py search "Toronto"
python contacts_tool.py list --json
```

**Step 5:** Push to GitHub.

---

## Checklist Before Moving On

- [ ] Supabase project created and configured
- [ ] Understand CRUD operations in SQL
- [ ] Created tables with proper types and constraints
- [ ] Understand Row Level Security (RLS) basics
- [ ] Connected Supabase to Claude Code (MCP or SDK)
- [ ] Built the contacts CLI tool exercise
- [ ] Pushed to GitHub

**All boxes checked?** You have a real database. Your AI agent can store and retrieve data. This is where things get serious.

---

**Next:** [Day 6 — Automation & Workflows](../day-06-automation-and-workflows/LESSON.md)
