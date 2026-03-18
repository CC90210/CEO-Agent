# Day 7: Deployment & Hosting — Going Live

> **Level:** Architect (Level 3) -- LEVEL UP!
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 6 complete
> **Goal:** Deploy a real application to the internet. Understand when to use what hosting.

---

## Module 1: Local vs Production (15 min)

### The Gap

| | Local (your computer) | Production (the internet) |
|---|---|---|
| **Who sees it** | Only you | Everyone |
| **Uptime** | When your laptop is open | 24/7/365 |
| **URL** | localhost:3000 | yourapp.com |
| **Speed** | Your internet | Server's internet (fast) |
| **Security** | Behind your firewall | Exposed to the world |
| **Cost** | Free | Free → $$$ depending on scale |

### The Deployment Decision Tree

```
Is it a website or web app?
├── YES → Static site (HTML/CSS/JS only)?
│   ├── YES → Vercel, Netlify, GitHub Pages (FREE)
│   └── NO → Has a backend/database?
│       ├── YES → Vercel + Supabase (free tier)
│       └── Needs custom server → VPS (Hostinger, DigitalOcean)
├── Is it a bot or background service?
│   └── YES → VPS or Docker container
└── Is it a workflow automation?
    └── YES → n8n on VPS (already covered Day 6)
```

---

## Module 2: Vercel (30 min)

### Why Vercel?

- Deploy in 30 seconds from GitHub
- Free tier handles most projects
- Auto-deploys when you push code
- Custom domains included
- Built for Next.js, React, Vue, etc.

### Deploy Your First App

**Step 1:** Make sure your project is on GitHub

**Step 2:** Go to https://vercel.com → Sign up with GitHub

**Step 3:** Click "Import Project" → Select your GitHub repo

**Step 4:** Configure:
- Framework Preset: auto-detected (or select manually)
- Build Command: usually `npm run build`
- Output Directory: usually `.next` or `build` or `dist`

**Step 5:** Click "Deploy"

In ~60 seconds, you get a URL: `your-project.vercel.app`

### Environment Variables in Vercel

Your .env file stays local. For production:
1. Go to Project Settings → Environment Variables
2. Add each key-value pair
3. Redeploy for changes to take effect

```
SUPABASE_URL = https://xxx.supabase.co
SUPABASE_ANON_KEY = eyJ...
STRIPE_PUBLIC_KEY = pk_live_...
```

### Custom Domains

1. Buy a domain (Namecheap, Cloudflare, Google Domains)
2. In Vercel: Project Settings → Domains → Add
3. Update DNS records at your domain registrar
4. Vercel handles SSL (HTTPS) automatically

### Auto-Deploy

Once connected to GitHub:
- Push to `main` → deploys to production
- Push to a branch → creates a preview deployment
- Every PR gets its own preview URL

---

## Module 3: Docker Basics (30 min)

### What Is Docker?

Docker packages your app and everything it needs into a **container** — a lightweight, portable box that runs the same everywhere.

**Without Docker:**
- "It works on my machine" → doesn't work on the server
- Different OS, different versions, different configs

**With Docker:**
- Package once → runs identically everywhere
- Your laptop, your server, your client's server — all the same

### Core Concepts

| Concept | Analogy | Purpose |
|---------|---------|---------|
| **Image** | A recipe | Blueprint for your container |
| **Container** | A dish made from the recipe | Running instance of your image |
| **Dockerfile** | The recipe card | Instructions to build the image |
| **Docker Hub** | A cookbook library | Public registry of images |

### Install Docker

- **Windows/Mac:** Download Docker Desktop from https://docker.com
- **Linux:** `sudo apt install docker.io`

**Verify:**
```bash
docker --version
docker run hello-world    # Downloads and runs a test container
```

### Your First Dockerfile

Create a simple Python app:

```python
# app.py
from http.server import HTTPServer, SimpleHTTPRequestHandler
print("Server running on port 8000")
HTTPServer(('', 8000), SimpleHTTPRequestHandler).serve_forever()
```

Create `Dockerfile`:
```dockerfile
# Start from Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy our code
COPY app.py .

# Tell Docker what port we use
EXPOSE 8000

# Run the app
CMD ["python", "app.py"]
```

### Build & Run

```bash
# Build the image
docker build -t my-first-app .

# Run it
docker run -p 8000:8000 my-first-app

# Visit http://localhost:8000
```

### Docker Compose (Multiple Services)

When you have multiple services (app + database + cache):

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://db:5432/myapp

  db:
    image: postgres:16
    environment:
      - POSTGRES_PASSWORD=mysecretpassword
    volumes:
      - db-data:/var/lib/postgresql/data

volumes:
  db-data:
```

```bash
# Start everything
docker compose up

# Stop everything
docker compose down
```

---

## Module 4: VPS Hosting (25 min)

### When You Need a VPS

A VPS (Virtual Private Server) is your own Linux server in the cloud. Use it when:
- Running services 24/7 (bots, n8n, background jobs)
- Need full control over the environment
- Running Docker containers in production
- Self-hosting tools (n8n, databases, etc.)

### Providers

| Provider | Starting Price | Best For |
|----------|---------------|----------|
| **Hostinger** | ~$5/month | Budget-friendly, good UI |
| **DigitalOcean** | $6/month | Developer-friendly |
| **Hetzner** | $4/month | Best price/performance (EU) |
| **AWS Lightsail** | $5/month | If you need AWS ecosystem |

### Basic VPS Setup

```bash
# Connect to your server
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install essentials
apt install -y git nodejs npm python3 python3-pip docker.io docker-compose

# Create a non-root user (security)
adduser deployer
usermod -aG sudo deployer
usermod -aG docker deployer

# Set up firewall
ufw allow 22     # SSH
ufw allow 80     # HTTP
ufw allow 443    # HTTPS
ufw enable
```

### Deploy with Docker on VPS

```bash
# On your VPS
git clone https://github.com/your-username/your-app.git
cd your-app
docker compose up -d    # -d = detached (runs in background)
```

---

## Module 5: Domains & DNS (15 min)

### How Domains Work

```
User types: myapp.com
    ↓
DNS lookup: "myapp.com → 123.45.67.89"
    ↓
Browser connects to that IP
    ↓
Your server responds with the website
```

### DNS Records

| Record | Purpose | Example |
|--------|---------|---------|
| **A** | Points domain to IP address | myapp.com → 123.45.67.89 |
| **CNAME** | Points subdomain to another domain | www.myapp.com → myapp.vercel.app |
| **MX** | Email routing | mail → gmail servers |
| **TXT** | Verification, SPF, DKIM | Domain ownership proof |

### Buying & Connecting

1. Buy domain at Namecheap (~$10/year) or Cloudflare ($9/year)
2. Point it to your host:
   - **Vercel:** Add CNAME record pointing to `cname.vercel-dns.com`
   - **VPS:** Add A record pointing to your server IP
3. SSL (HTTPS) is usually automatic (Let's Encrypt or host-provided)

---

## Module 6: CI/CD Basics (20 min)

### What Is CI/CD?

- **CI (Continuous Integration):** Automatically test code when pushed
- **CD (Continuous Deployment):** Automatically deploy code when tests pass

### The Flow

```
You push code to GitHub
    → GitHub Actions runs tests
    → Tests pass?
        → YES: Auto-deploy to Vercel/VPS
        → NO: Block the deploy, notify you
```

### GitHub Actions Basics

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm install

      - name: Run tests
        run: npm test

      - name: Build
        run: npm run build
```

Vercel auto-deploys from GitHub — no extra CI/CD needed for frontend. GitHub Actions is useful for running tests before deploy.

---

## Exercise: Deploy to the Internet

**Option A: Deploy to Vercel (Frontend)**

1. Take your Day 2 dashboard project
2. Push to GitHub (if not already)
3. Import into Vercel
4. Get your live URL
5. (Optional) Add a custom domain

**Option B: Dockerize a Python Script**

1. Take your Day 4 CLI tool
2. Create a Dockerfile for it
3. Build and run locally
4. Verify it works in the container

**Document your deployment:**
```bash
cd ~/ai-bootcamp/day-07
claude
```

Ask Claude Code:
```
Create a DEPLOYMENT.md that documents:
1. What was deployed and where (URL)
2. Environment variables needed
3. How to redeploy (step by step)
4. How to rollback if something breaks
```

Push to GitHub.

---

## Checklist Before Moving On

- [ ] Understand local vs production differences
- [ ] Deployed something to Vercel (or know how to)
- [ ] Understand Docker basics (images, containers, Dockerfile)
- [ ] Know when to use Vercel vs VPS vs Docker
- [ ] Understand domains and DNS basics
- [ ] Know what CI/CD is and how GitHub Actions works
- [ ] Completed deployment exercise
- [ ] Pushed documentation to GitHub

**All boxes checked?** You can deploy. Your projects aren't just local experiments — they're live on the internet.

---

**Next:** [Day 8 — Business Tools](../day-08-business-tools/LESSON.md)
