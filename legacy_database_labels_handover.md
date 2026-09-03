# Legacy Database Labeling Handover: Supabase ➡️ Turso

## 🎯 The Mistake to Track and Fix
During a recent session, an AI agent got confused and incorrectly reported that it was inserting data into **Supabase**, rather than the actual live database engine, **Turso**. 

This hallucination occurred because the system was originally built on Supabase. Although the underlying architecture was successfully migrated to Turso (libSQL), many of the python scripts in this repository still contain outdated `Supabase` naming conventions in their code, comments, docstrings, and print statements. 

For example, `scripts/scrape_firecrawl_leads.py` imports a legacy `supabase_tool` (which uses a `turso_supabase_compat` layer to secretly route the data to Turso) and its docstrings still say `"Insert to Supabase"`.

## 🛠️ Your Objective: The Great Codebase Audit
As the next AI picking up this task, your job is to audit the codebase and correct this technical debt so that future agents are not misled.

**Action Items:**
1. **Grep the Codebase:** Run a global search across the `scripts/` directory for the word `supabase` (case-insensitive).
2. **Update Docstrings & Comments:** Anywhere a script claims to be "inserting to Supabase" or "fetching from Supabase", update the text to accurately state **Turso**.
3. **Update Print Statements & Logs:** Ensure no scripts output misleading success messages like `"inserted_to_supabase"`.
4. **Gradual Refactoring (Optional but Recommended):** You will notice many scripts still import `scripts/integrations/supabase_tool.py`. As per that file's own docstring, it is officially deprecated. If you are deeply modifying a script, consider refactoring it to use the new standard: `scripts/integrations/turso_tool.py`.
5. **Internalize This For Yourself:** Remember that *you* are operating on Turso. Any references to Supabase in older code are purely legacy wrappers.

## 📝 Immediate Starting Point
Start by fixing the top of `scripts/scrape_firecrawl_leads.py`. 
- **Lines 8-9:** Update the pipeline documentation which still says "Dedup against existing Supabase leads" and "Insert to Supabase".
- **Global Search:** Then, move on to a workspace-wide `grep` search to hunt down the rest. 

Do not stop until the codebase accurately reflects its true Turso architecture!
