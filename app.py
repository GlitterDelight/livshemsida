#!/usr/bin/env python3
"""
Portfolio CMS server — serves the static site and provides /login + /admin
for creating subpages. Pure Python stdlib, no dependencies.
"""
import cgi
import hashlib
import json
import mimetypes
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
PAGES_DIR = BASE_DIR / "pages"
CONFIG_FILE = BASE_DIR / "admin_config.json"
SECRET_FILE = BASE_DIR / ".secret_key"

PAGES_INDEX = PAGES_DIR / "index.json"

UPLOAD_DIR.mkdir(exist_ok=True)
PAGES_DIR.mkdir(exist_ok=True)

CATEGORIES = {"projects": "Projects", "collaborations": "Collaborations", "contact": "Contact"}
CATEGORY_BACK = {"projects": "/projects.html", "collaborations": "/collaborations.html", "contact": "/contact.html"}

# ── session store ──────────────────────────────────────────────────────────
_sessions: dict = {}

def _secret_key() -> str:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_FILE.write_text(key)
    return key

_SECRET = _secret_key()

def _create_session() -> str:
    token = secrets.token_hex(32)
    _sessions[token] = {"logged_in": True}
    return token

def _destroy_session(token: str):
    _sessions.pop(token, None)

def _get_token(headers) -> str:
    for part in headers.get("Cookie", "").split(";"):
        p = part.strip()
        if p.startswith("session="):
            return p[8:]
    return ""

def _is_auth(headers) -> bool:
    token = _get_token(headers)
    return bool(token and _sessions.get(token, {}).get("logged_in"))

# ── password ───────────────────────────────────────────────────────────────
def _load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _check_pw(pw: str) -> bool:
    stored = _load_config().get("password_hash")
    return bool(stored and _hash(pw) == stored)

# ── helpers ────────────────────────────────────────────────────────────────
def _esc(s) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def _slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-") or "page"

def _load_index() -> dict:
    return json.loads(PAGES_INDEX.read_text()) if PAGES_INDEX.exists() else {}

def _save_index(idx: dict):
    PAGES_INDEX.write_text(json.dumps(idx, indent=2))

def _list_pages() -> list:
    idx = _load_index()
    pages = []
    for f in sorted(PAGES_DIR.glob("*.html")):
        slug = f.stem
        meta = idx.get(slug, {})
        pages.append({"slug": slug, "title": meta.get("title", slug), "category": meta.get("category", "")})
    return pages

# ── HTML: login ────────────────────────────────────────────────────────────
def _login_html(error: str = "") -> bytes:
    err = f'<p class="error">{_esc(error)}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Admin login</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f0f0f;min-height:100vh;display:flex;align-items:center;justify-content:center;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:2.5rem 3rem;
  width:100%;max-width:360px}}
h1{{color:#fff;font-weight:300;letter-spacing:.15em;text-transform:uppercase;font-size:1.3rem;
  text-align:center;margin-bottom:2rem}}
input[type=password]{{width:100%;background:#111;border:1px solid #333;border-radius:8px;
  color:#fff;font-size:1rem;padding:.8rem 1rem;margin-bottom:1.2rem;outline:none}}
input[type=password]:focus{{border-color:#666}}
button{{width:100%;background:#fff;color:#111;border:none;border-radius:8px;font-size:1rem;
  font-weight:500;letter-spacing:.1em;padding:.85rem;cursor:pointer;text-transform:uppercase;
  transition:opacity .2s}}
button:hover{{opacity:.85}}
.error{{color:#e06060;font-size:.9rem;margin-bottom:1rem;text-align:center}}
</style>
</head>
<body>
<div class="card">
<h1>Admin</h1>
{err}
<form method="POST" action="/login">
<input type="password" name="password" placeholder="Password" autofocus/>
<button type="submit">Log in</button>
</form>
</div>
</body>
</html>""".encode()

# ── HTML: admin dashboard ──────────────────────────────────────────────────
_ADMIN_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f0f0f;color:#e0e0e0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  min-height:100vh;padding:2rem}
header{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:2.5rem;padding-bottom:1.5rem;border-bottom:1px solid #222}
header h1{color:#fff;font-weight:300;letter-spacing:.2em;text-transform:uppercase;font-size:1.4rem}
.logout{color:#aaa;text-decoration:none;font-size:.9rem;letter-spacing:.1em;
  text-transform:uppercase;border:1px solid #333;border-radius:6px;padding:.4rem .9rem;
  transition:all .2s}
.logout:hover{color:#fff;border-color:#666}
section{margin-bottom:3rem}
section h2{color:#fff;font-weight:300;font-size:1rem;letter-spacing:.15em;
  text-transform:uppercase;margin-bottom:1rem}
.pages-list{display:flex;flex-direction:column;gap:.6rem}
.page-item{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;
  padding:.9rem 1.2rem;display:flex;align-items:center;justify-content:space-between}
.page-item span{color:#ccc;font-size:.95rem}
.page-slug{color:#ccc;font-size:.95rem;text-decoration:none;transition:color .2s}
.page-slug:hover{color:#fff;text-decoration:underline}
.actions{display:flex;gap:.6rem;align-items:center}
.actions a{color:#aaa;text-decoration:none;font-size:.85rem;border:1px solid #333;
  border-radius:5px;padding:.3rem .7rem;transition:all .2s}
.actions a:hover{color:#fff;border-color:#555}
.del-btn{background:none;border:1px solid #5a2020;color:#c06060;border-radius:5px;
  font-size:.85rem;padding:.3rem .7rem;cursor:pointer;transition:all .2s}
.del-btn:hover{background:#5a2020;color:#fff}
.empty{color:#555;font-size:.9rem}
.editor{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:2rem}
.field{margin-bottom:1.5rem}
.field label{display:block;color:#888;font-size:.8rem;letter-spacing:.12em;
  text-transform:uppercase;margin-bottom:.5rem}
.field input[type=text]{width:100%;background:#111;border:1px solid #333;border-radius:8px;
  color:#fff;font-size:1rem;padding:.75rem 1rem;outline:none;transition:border-color .2s}
.field input[type=text]:focus{border-color:#555}
.url-preview{color:#555;font-size:.85rem;margin-top:.4rem}
.url-preview span{color:#888}
#blocks{display:flex;flex-direction:column;gap:.8rem;margin-bottom:1.2rem}
.block{background:#111;border:1px solid #2e2e2e;border-radius:8px;padding:1rem;
  display:flex;gap:.8rem;align-items:flex-start}
.block-body{flex:1;min-width:0}
.block-label{color:#666;font-size:.75rem;letter-spacing:.1em;text-transform:uppercase;
  margin-bottom:.5rem}
.block textarea{width:100%;background:transparent;border:none;color:#ddd;font-size:1rem;
  line-height:1.7;resize:vertical;min-height:120px;outline:none;font-family:inherit}
.block textarea::placeholder{color:#444}
.upload-area{border:2px dashed #333;border-radius:8px;padding:1.5rem;text-align:center;
  cursor:pointer;transition:border-color .2s;position:relative}
.upload-area:hover{border-color:#555}
.upload-area input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;
  width:100%;height:100%}
.upload-area p{color:#555;font-size:.9rem}
.preview-img{max-width:100%;max-height:220px;border-radius:6px;margin-top:.8rem;
  display:block;margin-left:auto;margin-right:auto}
.preview-vid{max-width:100%;max-height:220px;border-radius:6px;margin-top:.8rem;
  display:block;margin-left:auto;margin-right:auto}
.remove-btn{background:none;border:none;color:#555;font-size:1.2rem;cursor:pointer;
  padding:.2rem .4rem;line-height:1;border-radius:4px;transition:color .2s;flex-shrink:0}
.remove-btn:hover{color:#c06060}
.toolbar{display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:1.5rem}
.toolbar button{background:#1f1f1f;border:1px solid #333;color:#ccc;border-radius:8px;
  padding:.65rem 1.3rem;font-size:.9rem;cursor:pointer;transition:all .2s;letter-spacing:.05em}
.toolbar button:hover{background:#2a2a2a;color:#fff;border-color:#555}
.publish-btn{width:100%;background:#fff;color:#111;border:none;border-radius:8px;
  font-size:1rem;font-weight:500;letter-spacing:.12em;padding:1rem;cursor:pointer;
  text-transform:uppercase;transition:opacity .2s}
.publish-btn:hover{opacity:.85}
.field select{width:100%;background:#111;border:1px solid #333;border-radius:8px;
  color:#fff;font-size:1rem;padding:.75rem 1rem;outline:none;transition:border-color .2s;
  appearance:none;cursor:pointer}
.field select:focus{border-color:#555}
.cat-badge{font-size:.75rem;color:#888;border:1px solid #2a2a2a;border-radius:4px;
  padding:.15rem .5rem;margin-left:.5rem;text-transform:uppercase;letter-spacing:.08em}
</style>
</head>
<body>
<header>
  <h1>Admin</h1>
  <a class="logout" href="/logout">Log out</a>
</header>

<section>
  <h2>My pages</h2>
  <!--PAGES-->
</section>

<section>
  <h2>Create new page</h2>
  <div class="editor">
    <form id="createForm" method="POST" action="/admin/create">
      <input type="hidden" name="slug" id="slugInput"/>
      <input type="hidden" name="blocks" id="blocksInput"/>
      <div class="field">
        <label>Page title</label>
        <input type="text" name="title" id="titleInput"
          placeholder="e.g. Spring collection 2025" autocomplete="off"/>
        <div class="url-preview">
          URL: livmeijernordgren.com/pages/<span id="slugPreview">…</span>
        </div>
      </div>
      <div class="field">
        <label>Category</label>
        <select name="category" id="categoryInput">
          <option value="">— No category —</option>
          <option value="projects">Projects</option>
          <option value="collaborations">Collaborations</option>
          <option value="contact">Contact</option>
        </select>
      </div>
      <div class="field">
        <label>Content</label>
        <div id="blocks"></div>
        <div class="toolbar">
          <button type="button" onclick="addText()">+ Add text</button>
          <button type="button" onclick="addMedia('image')">+ Add image</button>
          <button type="button" onclick="addMedia('video')">+ Add video</button>
        </div>
      </div>
      <button type="button" class="publish-btn" onclick="publish()">Publish page</button>
    </form>
  </div>
</section>

<script>
let blockId = 0;

document.addEventListener('input', function(e) {
  if (e.target.classList.contains('auto-resize')) {
    e.target.style.height = 'auto';
    e.target.style.height = e.target.scrollHeight + 'px';
  }
});

function slugify(s) {
  return s.toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'page';
}

document.getElementById('titleInput').addEventListener('input', function() {
  const slug = slugify(this.value);
  document.getElementById('slugPreview').textContent = slug || '…';
  document.getElementById('slugInput').value = slug;
});

function makeRemoveBtn(target) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'remove-btn';
  btn.title = 'Remove';
  btn.textContent = '✕';
  btn.addEventListener('click', function() { target.remove(); });
  return btn;
}

function addText() {
  const id = ++blockId;
  const div = document.createElement('div');
  div.className = 'block';
  div.dataset.type = 'text';
  div.dataset.id = id;

  const body = document.createElement('div');
  body.className = 'block-body';

  const lbl = document.createElement('div');
  lbl.className = 'block-label';
  lbl.textContent = 'Text';

  const ta = document.createElement('textarea');
  ta.className = 'auto-resize';
  ta.placeholder = 'Write something\u2026';

  body.appendChild(lbl);
  body.appendChild(ta);
  div.appendChild(body);
  div.appendChild(makeRemoveBtn(div));
  document.getElementById('blocks').appendChild(div);
  ta.focus();
}

function addMedia(type) {
  const id = ++blockId;
  const label = type === 'image' ? 'Image' : 'Video';
  const accept = type === 'image' ? 'image/*' : 'video/*';

  const div = document.createElement('div');
  div.className = 'block';
  div.dataset.type = type;
  div.dataset.id = id;
  div.dataset.url = '';

  const body = document.createElement('div');
  body.className = 'block-body';

  const lbl = document.createElement('div');
  lbl.className = 'block-label';
  lbl.textContent = label;

  const area = document.createElement('div');
  area.className = 'upload-area';
  area.id = 'ua' + id;

  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = accept;
  inp.addEventListener('change', function() { uploadFile(this, id, type); });

  const p = document.createElement('p');
  p.textContent = 'Click to choose a ' + label.toLowerCase();

  area.appendChild(inp);
  area.appendChild(p);
  body.appendChild(lbl);
  body.appendChild(area);
  div.appendChild(body);
  div.appendChild(makeRemoveBtn(div));
  document.getElementById('blocks').appendChild(div);
}

function uploadFile(input, id, type) {
  const file = input.files[0];
  if (!file) return;
  const area = document.getElementById('ua' + id);
  area.querySelector('p').textContent = 'Uploading\u2026';
  const fd = new FormData();
  fd.append('file', file);
  fetch('/admin/upload', {method: 'POST', body: fd})
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) { area.querySelector('p').textContent = 'Upload failed.'; return; }
      const block = area.closest('.block');
      block.dataset.url = data.url;
      area.querySelector('p').textContent = file.name;
      if (type === 'image') {
        const img = document.createElement('img');
        img.className = 'preview-img';
        img.src = data.url;
        area.appendChild(img);
      } else {
        const vid = document.createElement('video');
        vid.className = 'preview-vid';
        vid.controls = true;
        vid.src = data.url;
        area.appendChild(vid);
      }
    })
    .catch(function() { area.querySelector('p').textContent = 'Upload failed \u2014 try again'; });
}

function publish() {
  const title = document.getElementById('titleInput').value.trim();
  if (!title) { alert('Please enter a page title.'); return; }

  const blockDivs = document.getElementById('blocks').querySelectorAll('.block');
  if (!blockDivs.length) { alert('Please add at least one content block.'); return; }

  const blocks = [];
  let valid = true;
  blockDivs.forEach(function(div) {
    if (!valid) return;
    const type = div.dataset.type;
    if (type === 'text') {
      const text = div.querySelector('textarea').value.trim();
      if (text) blocks.push({type: 'text', content: text});
    } else {
      const url = div.dataset.url;
      if (!url) {
        alert('Please wait for uploads to finish, or remove empty media blocks.');
        valid = false;
        return;
      }
      blocks.push({type: type, url: url});
    }
  });

  if (!valid) return;
  if (!blocks.length) { alert('Please add some content.'); return; }

  document.getElementById('blocksInput').value = JSON.stringify(blocks);
  document.getElementById('createForm').submit();
}
</script>
</body>
</html>"""

def _admin_html() -> bytes:
    pages = _list_pages()
    if pages:
        def _row(p):
            cat = p.get("category", "")
            badge = ('<span class="cat-badge">' + _esc(CATEGORIES[cat]) + '</span>') if cat in CATEGORIES else ""
            return (
                '<div class="page-item">'
                '<span>'
                '<a href="/pages/' + _esc(p["slug"]) + '" target="_blank" class="page-slug">' + _esc(p["title"]) + '</a>'
                + badge +
                '</span>'
                '<div class="actions">'
                '<form method="POST" action="/admin/delete" style="display:inline">'
                '<input type="hidden" name="slug" value="' + _esc(p["slug"]) + '"/>'
                '<button type="submit" class="del-btn"'
                ' onclick="return confirm(\'Delete this page?\')">Delete</button>'
                '</form>'
                '</div></div>'
            )
        pages_html = '<div class="pages-list">' + "".join(_row(p) for p in pages) + '</div>'
    else:
        pages_html = '<p class="empty">No pages created yet.</p>'
    return _ADMIN_TEMPLATE.replace('<!--PAGES-->', pages_html).encode()

# ── HTML: generated page ───────────────────────────────────────────────────
def _generate_page(title: str, blocks: list, category: str = "") -> str:
    blocks_html = ""
    for b in blocks:
        t = b.get("type")
        if t == "text":
            blocks_html += f'<p class="block-text">{_esc(b.get("content", ""))}</p>\n'
        elif t == "image":
            blocks_html += f'<div class="block-image"><img src="{_esc(b.get("url",""))}" alt=""/></div>\n'
        elif t == "video":
            url = _esc(b.get("url", ""))
            blocks_html += (
                f'<div class="block-video">'
                f'<video controls playsinline><source src="{url}"/></video>'
                f'</div>\n'
            )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(title)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f0f0f;color:#e0e0e0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  min-height:100vh;padding:5rem 2rem 4rem}}
.back{{position:fixed;top:1rem;left:1.5rem;color:#fff;font-size:2rem;
  text-decoration:none;opacity:.7;transition:opacity .2s;z-index:10}}
.back:hover{{opacity:1}}
h1{{text-align:center;font-weight:300;letter-spacing:.2em;text-transform:uppercase;
  font-size:clamp(1.5rem,4vw,3rem);margin-bottom:3rem;color:#fff}}
.content{{max-width:800px;margin:0 auto}}
.block-text{{font-size:1.1rem;line-height:1.8;margin-bottom:2rem;white-space:pre-wrap}}
.block-image,.block-video{{margin-bottom:2rem;text-align:center}}
.block-image img,.block-video video{{max-width:100%;height:auto;border-radius:4px}}
</style>
</head>
<body>
<a class="back" href="{_esc(CATEGORY_BACK.get(category, '/home.html'))}">←</a>
<h1>{_esc(title)}</h1>
<div class="content">
{blocks_html}</div>
</body>
</html>"""

# ── request handler ────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send_html(self, body: bytes, status: int = 200, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, extra_headers=None):
        self.send_response(302)
        self.send_header("Location", location)
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path):
        # Try with .html extension if the exact path doesn't exist
        if not path.exists() and not str(path).endswith(".html"):
            path = Path(str(path) + ".html")
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        if path.is_dir():
            # Serve a simple directory listing so home.html thumbnail scripts work
            files = sorted(path.iterdir(), key=lambda f: f.name)
            links = "".join(f'<a href="{_esc(f.name)}">{_esc(f.name)}</a>\n' for f in files if f.is_file())
            body = f"<html><body>{links}</body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        mime, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _parse_urlencoded(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode(errors="replace")
        parsed = parse_qs(body, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/login", "/login/"):
            self._send_html(_login_html())

        elif path in ("/logout", "/logout/"):
            token = _get_token(self.headers)
            if token:
                _destroy_session(token)
            self._redirect("/", [("Set-Cookie", "session=; Max-Age=0; Path=/")])

        elif path in ("/admin", "/admin/"):
            if not _is_auth(self.headers):
                self._redirect("/login")
            else:
                self._send_html(_admin_html())

        elif path == "/api/pages":
            qs = parse_qs(urlparse(self.path).query)
            cat_filter = qs.get("category", [None])[0]
            idx = _load_index()
            result = []
            for slug, meta in idx.items():
                if (PAGES_DIR / f"{slug}.html").exists():
                    if cat_filter is None or meta.get("category") == cat_filter:
                        result.append({"slug": slug, "title": meta.get("title", slug),
                                       "category": meta.get("category", ""),
                                       "thumbnail": meta.get("thumbnail", "")})
            self._send_json(result)

        else:
            rel = unquote(path.lstrip("/"))
            self._serve_file(BASE_DIR / rel if rel else BASE_DIR / "index.html")

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/login":
            form = self._parse_urlencoded()
            if _check_pw(form.get("password", "")):
                token = _create_session()
                cookie = f"session={token}; Path=/; HttpOnly; SameSite=Lax"
                self._redirect("/admin", [("Set-Cookie", cookie)])
            else:
                self._send_html(_login_html("Wrong password"))

        elif path == "/admin/upload":
            if not _is_auth(self.headers):
                self._send_json({"error": "Not logged in"}, 401)
                return
            ct = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ct:
                self._send_json({"error": "Expected multipart"}, 400)
                return
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                fs = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": ct,
                        "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                    },
                )
            if "file" not in fs or not fs["file"].filename:
                self._send_json({"error": "No file"}, 400)
                return
            item = fs["file"]
            filename = re.sub(r"[^\w.\-]", "_", os.path.basename(item.filename))
            name, ext = os.path.splitext(filename)
            unique = f"{name}_{secrets.token_hex(4)}{ext}"
            (UPLOAD_DIR / unique).write_bytes(item.file.read())
            self._send_json({"url": f"/uploads/{unique}"})

        elif path == "/admin/create":
            if not _is_auth(self.headers):
                self._redirect("/login")
                return
            form = self._parse_urlencoded()
            title = form.get("title", "Untitled").strip()
            slug = _slugify(form.get("slug", "") or title)
            category = form.get("category", "") if form.get("category", "") in CATEGORIES else ""
            try:
                blocks = json.loads(form.get("blocks", "[]"))
            except json.JSONDecodeError:
                blocks = []
            out = PAGES_DIR / f"{slug}.html"
            if out.exists():
                slug = f"{slug}-{secrets.token_hex(3)}"
                out = PAGES_DIR / f"{slug}.html"
            out.write_text(_generate_page(title, blocks, category))
            # Save metadata
            thumbnail = next((b["url"] for b in blocks if b.get("type") == "image" and b.get("url")), "")
            idx = _load_index()
            idx[slug] = {"title": title, "category": category, "thumbnail": thumbnail}
            _save_index(idx)
            self._redirect("/admin")

        elif path == "/admin/delete":
            if not _is_auth(self.headers):
                self._redirect("/login")
                return
            form = self._parse_urlencoded()
            slug = re.sub(r"[^\w-]", "", form.get("slug", ""))
            p = PAGES_DIR / f"{slug}.html"
            if p.exists():
                p.unlink()
            idx = _load_index()
            idx.pop(slug, None)
            _save_index(idx)
            self._redirect("/admin")

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    print("Serving on http://0.0.0.0:8080")
    server.serve_forever()
