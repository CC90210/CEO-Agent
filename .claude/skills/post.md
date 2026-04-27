---
name: post
description: Publish content to social media via Late MCP. Handles scheduling, cross-posting, character limit validation, and media uploads.
user-invocable: true
---

# /post — Social Media Publishing

## Steps

1. Get content from CC (inline text or from a previous `/content` draft).

2. Ask CC which platform(s) and when (now / scheduled time).

3. **Validate character limits** BEFORE posting:
   - X/Twitter: 280 chars
   - Threads: 500 chars
   - Instagram: 2200 chars
   - LinkedIn: 3000 chars
   - TikTok: 4000 chars

4. If media is needed:
   - `media_generate_upload_link` → get upload URL
   - Upload the file
   - `media_check_upload_status` → confirm ready

5. Get the account/profile IDs:
   - `accounts_list` → find the target platform account
   - `profiles_list` → find the profile if cross-posting

6. Create the post:
   - Single platform: `posts_create`
   - Multiple platforms: `posts_cross_post`

7. Confirm to CC with post ID and scheduled time.
