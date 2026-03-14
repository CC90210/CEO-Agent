---
description: Publish a social media post to one or multiple platforms via Late API
---
// turbo-all

## Steps

1. Ask CC for the post content (or use provided content).

2. Check connected accounts:
   - Call `mcp_late_accounts_list` to see which platforms are connected.

3. Ask CC which platform(s) to post to. Options: twitter, instagram, linkedin, tiktok, bluesky, facebook, youtube, pinterest, threads.

4. Validate character limits before posting:
   - X/Twitter: 280 chars
   - LinkedIn: 3000 chars
   - Instagram: 2200 chars
   - Threads: 500 chars
   - TikTok: 4000 chars
   - If over limit, trim and confirm with CC.

5. If CC wants media, call `mcp_late_media_generate_upload_link` and have CC upload files, then `mcp_late_media_check_upload_status` to get URLs.

6. Post the content:
   - Single platform: `mcp_late_posts_create` with `publish_now=true` or schedule with `schedule_minutes`.
   - Multiple platforms: `mcp_late_posts_cross_post` with comma-separated platforms.

7. Confirm to CC: "Posted to [platforms]. Post ID: [id]."
