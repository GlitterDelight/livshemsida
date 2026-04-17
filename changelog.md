# Changelog

## 2026-04-16
- Initial portfolio template created (index.html, style.css)
- Simplified site to three centered navigation categories: Projects, Own Work, About
- Set up systemd service (livshemsida.service) to serve site on port 8080
- Connected to GitHub repo: https://github.com/GlitterDelight/livshemsida.git
- Configured Nginx Proxy Manager and Cloudflare for livmeijernordgren.com
- Set up NAS dataset (molnenge_livshemsida) with SMB share; symlinked projects, collaborations, contact, images, videos into site directory
- Added three-panel navigation page (home.html) with Projects, Collaborations, Contact sections loading thumbnails from NAS
- Added slideshow subpages (projects.html, collaborations.html, contact.html) cycling images from NAS folders with live refresh
- Renamed "About" category to "Contact" with matching folder rename
- Added video landing page (index.html) with fullscreen dyngbaggen.mp4 background and centered "Enter" link to home.html
