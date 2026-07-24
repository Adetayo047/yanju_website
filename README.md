# Yanju Foundation Website

Static site + a small Python backend for the Yanju Foundation, a Nigerian non-profit empowering youth through education, mentorship, and community outreach.

## What's in here

- **Pages**: `index.html`, `about.html`, `programs.html`, `gallery.html`, `success-stories.html`, `volunteer.html`, `donate.html`, `sponsor.html`, `faq.html`
- **`admin.html`**: password-protected dashboard for staff to view volunteer applications, donation pledges, newsletter signups, and manage gallery photos
- **`server.py`**: serves the static pages and exposes a small JSON API — no third-party Python packages, standard library only
- **`assets/`**: shared CSS/JS (`enhance.js`, `enhance.css`), the logo, and real photos (team headshots, testimonials, program/gallery images)

## Backend (`server.py`)

Everything the site needs beyond static files runs through this one script:

| Route | Purpose |
|---|---|
| `POST /api/chat` | Proxies the site's AI assistant widget to OpenAI |
| `POST /api/volunteer` | Saves volunteer applications to Supabase |
| `POST /api/newsletter` | Saves newsletter signups to Supabase |
| `POST /api/donate-pledge` | Saves donation pledges to Supabase (in addition to the `mailto:` confirmation) |
| `GET /api/gallery` | Public list of gallery photos, used by `gallery.html` |
| `POST /api/admin/login` / `logout` | Session-cookie based admin auth |
| `GET /api/admin/volunteers` / `pledges` / `newsletter` | Protected — data for the admin dashboard |
| `POST` / `DELETE /api/admin/gallery` | Protected — upload/delete gallery photos (Supabase Storage) |

Database: [Supabase](https://supabase.com) (Postgres + Storage), accessed over plain HTTPS via `urllib` — no ORM, no `psycopg2`. Email notifications on new submissions go out via Gmail SMTP (`smtplib`, standard library).

## Running locally

```bash
cp .env.example .env   # fill in real values
python3 server.py
```

Open `http://localhost:8742`.

### Required environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Powers the AI assistant chat widget |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Database + Storage for forms and the gallery |
| `ADMIN_PASSWORD` | Login password for `/admin.html` |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` / `NOTIFY_EMAIL` | Optional — email notification on new form submissions |

`.env` is gitignored; never commit real secrets. See `.env.example` for the template.

### Supabase setup

Run the SQL to create `volunteer_applications`, `newsletter_signups`, `gallery_images`, and `donation_pledges` tables (with RLS enabled — only the service_role key can read/write), and create a public Storage bucket named `gallery`.

## Deployment

Deployed on [Render](https://render.com) as a Python web service:
- **Build command**: `pip install -r requirements.txt` (no dependencies — the file exists so Render's build step has something to run)
- **Start command**: `python3 server.py`
- Environment variables set in Render's dashboard (same list as above)
- Custom domain (`yanjufoundation.com`) DNS pointed at Render, registrar-agnostic (currently registered via GoDaddy)
