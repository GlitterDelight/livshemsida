# Changelog

## 2026-04-27 — Page editing, image gallery, category list layout & mobile fix

### New features
- **Page editing** (`/admin/edit`): Existing pages can now be edited from the admin panel. An "Edit" button appears next to each page in the list. The edit form is pre-filled with the existing title, category, text blocks, and media. Block data is now stored in `pages/index.json` alongside title and category.
- **Image gallery with lightbox** (generated pages): All images on a page are collected into a responsive grid gallery at the top. Clicking a thumbnail opens the full image in a lightbox overlay. Close by clicking anywhere or pressing Escape.
- **Category page list layout** (`projects.html`, `collaborations.html`, `contact.html`): Category pages now display pages as a vertical list with a small thumbnail (100×65px) to the left of the title, replacing the old full-screen nav-panel style.

### Fixes
- **Mobile home page invisible** (`style.css`): Nav items were invisible on mobile because the `@media (max-width: 768px)` block appeared before the `.nav-item` base styles in the CSS file. Since both rules had equal specificity, the later `flex: 1` overrode `flex: none` from the media query. Fixed by moving the media query after the base styles.

### Technical notes
- CSS and static HTML files are now editable directly via sshfs since project directory ownership was changed to `truenas_admin`.
- Service configured to run as `truenas_admin` (instead of root) via `User=` in the systemd unit file, allowing process-based restarts without sudo.
- `.claude/` added to `.gitignore`.

## 2026-04-18 — Admin CMS & Category Pages

### New features
- **Admin CMS** (`app.py`, `/admin`): Password-protected page builder. Login with a hashed password stored in `admin_config.json`. Create subpages with a title, category, and any mix of text blocks and image/video uploads. Pages are listed in the admin panel with a link to open each in a new tab. Pages can be deleted.
- **`set_password.py`**: Run `python3 set_password.py <password>` to set the admin password.
- **Category pages** (`projects.html`, `collaborations.html`, `contact.html`): Each category page now fetches its pages from `/api/pages?category=X` and displays them as nav panels (same visual style as the home page), with thumbnail images and titles. Shows "No pages yet." when empty.
- **`/api/pages` endpoint**: Returns JSON list of pages, optionally filtered by `?category=`.

### Fixes
- **White hairline gap between nav panels on home page**: Switched from `<img>` elements to CSS `background-image` set via JavaScript. The gap was caused by the browser rendering inline images with a sub-pixel gap that no CSS fix could eliminate.
- **Concurrent requests blocking navigation**: Switched from single-threaded `HTTPServer` to `ThreadingHTTPServer` so video streaming no longer blocks page navigation.
- **Directory listing for thumbnail loading**: The new server re-added directory listing support needed by the home page thumbnail JS.
- **Mobile image display**: Fixed mobile Safari issue where CSS custom property `var(--thumb)` on `::before` was unreliable — now sets `backgroundImage` directly on the element.

### Known issues / deferred
- **Mobile zoom**: On mobile, nav panel images appear zoomed in (`background-size: cover` on 56vw-tall portrait panels crops landscape images). Deferred to next session.

### Technical notes
- Backend uses Python stdlib only (no Flask/pip) — required by TrueNAS environment.
- Admin HTML template uses a raw string (`r"""..."""`) and DOM `createElement` calls to avoid f-string/JavaScript quoting conflicts.
- Sensitive files excluded from git: `admin_config.json`, `.secret_key`, `venv/`, `uploads/`, `pages/`.
