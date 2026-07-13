#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from athanasor.benchmark.reviewer import ReviewSession, ReviewerError


MAX_REQUEST_BYTES = 64 * 1024


def _page(token: str) -> bytes:
    nonce = html.escape(token, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Azoth adjudication ledger</title>
  <style nonce="{nonce}">
    :root {{
      --ink: #14213d;
      --ink-soft: #42506a;
      --paper: #edf2f8;
      --panel: #ffffff;
      --line: #b9c6d8;
      --cobalt: #2856c7;
      --cobalt-dark: #17398b;
      --mint: #d7f1e5;
      --mint-ink: #0b5c3d;
      --danger: #a93232;
      --shadow: 0 18px 48px rgba(20, 33, 61, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(40,86,199,.055) 1px, transparent 1px) 0 0 / 24px 24px,
        var(--paper);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      line-height: 1.48;
    }}
    button, input, textarea {{ font: inherit; }}
    button:focus-visible, input:focus-visible, textarea:focus-visible {{
      outline: 3px solid #80a6ff;
      outline-offset: 2px;
    }}
    .shell {{ max-width: 1240px; margin: 0 auto; padding: 28px 28px 48px; }}
    .masthead {{
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: end;
      gap: 24px;
      margin-bottom: 18px;
    }}
    .eyebrow {{
      margin: 0 0 5px;
      color: var(--cobalt-dark);
      font: 700 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-family: Charter, Georgia, serif;
      font-size: clamp(34px, 5vw, 62px);
      font-weight: 600;
      letter-spacing: -.045em;
      line-height: .95;
    }}
    .counter {{ text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .counter strong {{ display: block; font-size: 22px; }}
    .counter span {{ color: var(--ink-soft); font-size: 12px; }}
    .progress-track {{ height: 8px; border: 1px solid var(--line); background: #fff; margin-bottom: 26px; }}
    .progress-fill {{ height: 100%; width: 0; background: var(--cobalt); transition: width .22s ease; }}
    .papers {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .paper {{ background: var(--panel); border: 1px solid var(--line); box-shadow: var(--shadow); }}
    .paper-head {{ padding: 22px 24px 18px; border-bottom: 1px solid var(--line); }}
    .paper-mark {{
      display: inline-grid;
      place-items: center;
      width: 30px;
      height: 30px;
      margin-bottom: 14px;
      border-radius: 50%;
      color: #fff;
      background: var(--ink);
      font: 700 13px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    h2 {{ margin: 0 0 8px; font-family: Charter, Georgia, serif; font-size: 25px; line-height: 1.14; }}
    .authors {{ margin: 0; color: var(--ink-soft); font-size: 13px; }}
    .evidence-title {{ margin: 0; padding: 15px 24px 8px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    .evidence-list {{ display: grid; gap: 8px; padding: 0 14px 18px; }}
    .evidence-item {{
      display: grid;
      grid-template-columns: 24px 1fr;
      gap: 10px;
      align-items: start;
      padding: 11px 12px;
      border: 1px solid transparent;
      border-radius: 8px;
      color: #27344e;
      background: #f5f7fb;
      cursor: pointer;
      font-size: 14px;
    }}
    .evidence-item:hover {{ border-color: var(--line); }}
    .evidence-item:has(input:checked) {{ border-color: var(--cobalt); background: #e9efff; }}
    .evidence-item input {{ width: 18px; height: 18px; margin: 1px 0 0; accent-color: var(--cobalt); }}
    .judgment {{ margin-top: 20px; padding: 24px; background: var(--ink); color: #fff; box-shadow: var(--shadow); }}
    .judgment h3 {{ margin: 0 0 15px; font-family: Charter, Georgia, serif; font-size: 26px; }}
    .labels {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
    .label-card {{
      position: relative;
      display: grid;
      grid-template-columns: 30px 1fr;
      gap: 10px;
      min-height: 108px;
      padding: 14px;
      border: 1px solid #62708d;
      background: #1d2c4d;
      cursor: pointer;
    }}
    .label-card:has(input:checked) {{ border-color: #9eb8ff; background: var(--cobalt-dark); box-shadow: inset 0 0 0 2px #9eb8ff; }}
    .label-card input {{ position: absolute; opacity: 0; }}
    .tick {{
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border: 2px solid #8794ae;
      border-radius: 4px;
      color: transparent;
      font-weight: 900;
    }}
    .label-card:has(input:checked) .tick {{ color: var(--ink); border-color: #fff; background: #fff; }}
    .label-number {{ display: block; margin-bottom: 4px; color: #c9d6f5; font: 700 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .label-copy {{ font-size: 13px; line-height: 1.35; }}
    .rationale-wrap {{ margin-top: 18px; }}
    .rationale-wrap label {{ display: block; margin-bottom: 7px; font-size: 13px; font-weight: 700; }}
    textarea {{
      width: 100%;
      min-height: 94px;
      padding: 13px 14px;
      resize: vertical;
      border: 1px solid #71809c;
      border-radius: 6px;
      color: var(--ink);
      background: #fff;
    }}
    .actions {{ display: flex; align-items: center; gap: 10px; margin-top: 16px; }}
    .actions button {{
      min-height: 44px;
      padding: 0 18px;
      border: 1px solid #8da0c7;
      border-radius: 5px;
      color: #fff;
      background: transparent;
      cursor: pointer;
      font-weight: 700;
    }}
    .actions button.primary {{ color: var(--ink); border-color: #fff; background: #fff; }}
    .actions button:disabled {{ opacity: .38; cursor: not-allowed; }}
    .status {{ margin-left: auto; color: #c9d6f5; font-size: 13px; }}
    .status.saved {{ color: #86e0b5; }}
    .status.error {{ color: #ffb4b4; }}
    .privacy {{ margin: 14px 2px 0; color: var(--ink-soft); font-size: 12px; }}
    @media (max-width: 850px) {{
      .papers, .labels {{ grid-template-columns: 1fr; }}
      .masthead {{ align-items: start; }}
      .label-card {{ min-height: auto; }}
    }}
    @media (max-width: 540px) {{
      .shell {{ padding: 18px 14px 34px; }}
      .masthead {{ grid-template-columns: 1fr; }}
      .counter {{ text-align: left; }}
      .actions {{ flex-wrap: wrap; }}
      .status {{ width: 100%; margin-left: 0; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ .progress-fill {{ transition: none; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="masthead">
      <div><p class="eyebrow">Azoth · private adjudication</p><h1 id="heading">Pair review</h1></div>
      <div class="counter"><strong id="position">— / —</strong><span id="completed">— completed</span></div>
    </header>
    <div class="progress-track" aria-hidden="true"><div class="progress-fill" id="progress"></div></div>
    <section class="papers" aria-label="Blinded paper pair">
      <article class="paper">
        <div class="paper-head"><span class="paper-mark">A</span><h2 id="title-a"></h2><p class="authors" id="authors-a"></p></div>
        <h3 class="evidence-title">Tick evidence from paper A</h3><div class="evidence-list" id="evidence-a"></div>
      </article>
      <article class="paper">
        <div class="paper-head"><span class="paper-mark">B</span><h2 id="title-b"></h2><p class="authors" id="authors-b"></p></div>
        <h3 class="evidence-title">Tick evidence from paper B</h3><div class="evidence-list" id="evidence-b"></div>
      </article>
    </section>
    <section class="judgment">
      <h3>Record your judgment</h3>
      <div class="labels" role="radiogroup" aria-label="Relationship label">
        <label class="label-card"><input id="label-0" type="radio" name="label" value="0"><span class="tick">✓</span><span><b class="label-number">0 · NONE</b><span class="label-copy">No meaningful structural relationship.</span></span></label>
        <label class="label-card"><input id="label-1" type="radio" name="label" value="1"><span class="tick">✓</span><span><b class="label-number">1 · SURFACE</b><span class="label-copy">Topical or lexical overlap without an actionable structural relation.</span></span></label>
        <label class="label-card"><input id="label-2" type="radio" name="label" value="2"><span class="tick">✓</span><span><b class="label-number">2 · STRUCTURAL</b><span class="label-copy">Meaningful shared mechanism, method, or decision structure.</span></span></label>
        <label class="label-card"><input id="label-3" type="radio" name="label" value="3"><span class="tick">✓</span><span><b class="label-number">3 · TRANSFERABLE</b><span class="label-copy">Strong structural relation with a concrete transferable implication.</span></span></label>
      </div>
      <div class="rationale-wrap"><label for="rationale">Brief rationale</label><textarea id="rationale" placeholder="A few precise words are enough." required></textarea></div>
      <div class="actions">
        <button id="back" type="button">Back</button>
        <button id="save" type="button">Save</button>
        <button class="primary" id="save-next" type="button">Save &amp; next</button>
        <span class="status" id="status" role="status" aria-live="polite"></span>
      </div>
    </section>
    <p class="privacy">Local only · private answers are written atomically · hidden benchmark metadata is not shown</p>
  </main>
  <script nonce="{nonce}">
    const base = location.pathname;
    const rubricInputs = [...document.querySelectorAll('input[name="label"]')];
    const statusEl = document.getElementById('status');
    let current = 0;
    let total = 0;
    let dirty = false;
    let busy = false;

    function setStatus(message, kind = '') {{
      statusEl.textContent = message;
      statusEl.className = `status ${{kind}}`;
    }}
    function markDirty() {{ dirty = true; setStatus('Unsaved changes'); }}
    function evidenceList(role, sentences, selected) {{
      const root = document.getElementById(`evidence-${{role}}`);
      root.replaceChildren();
      sentences.forEach((sentence, index) => {{
        const label = document.createElement('label');
        label.className = 'evidence-item';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = sentence;
        input.checked = selected.includes(sentence);
        input.addEventListener('change', markDirty);
        input.setAttribute('aria-label', `Paper ${{role.toUpperCase()}} evidence ${{index + 1}}`);
        const text = document.createElement('span');
        text.textContent = sentence;
        label.append(input, text);
        root.append(label);
      }});
    }}
    async function load(index) {{
      if (busy) return;
      busy = true;
      setStatus('Loading…');
      try {{
        const response = await fetch(`${{base}}api/presentation/${{index}}`, {{cache: 'no-store'}});
        if (!response.ok) throw new Error((await response.json()).error || 'Could not load this pair.');
        const view = await response.json();
        current = index;
        total = view.total;
        document.getElementById('position').textContent = `${{view.position}} / ${{view.total}}`;
        document.getElementById('completed').textContent = `${{view.completed}} completed`;
        document.getElementById('progress').style.width = `${{(view.completed / view.total) * 100}}%`;
        document.getElementById('title-a').textContent = view.paper_a.title;
        document.getElementById('authors-a').textContent = view.paper_a.authors.join(', ');
        document.getElementById('title-b').textContent = view.paper_b.title;
        document.getElementById('authors-b').textContent = view.paper_b.authors.join(', ');
        evidenceList('a', view.paper_a.evidence, view.answer.evidence.a);
        evidenceList('b', view.paper_b.evidence, view.answer.evidence.b);
        rubricInputs.forEach(input => input.checked = Number(input.value) === view.answer.label);
        document.getElementById('rationale').value = view.answer.rationale;
        document.getElementById('back').disabled = current === 0;
        document.getElementById('save-next').textContent = current + 1 === total ? 'Save final answer' : 'Save & next';
        dirty = false;
        setStatus(view.answer.label === null ? 'Not yet saved' : 'Saved', view.answer.label === null ? '' : 'saved');
      }} catch (error) {{ setStatus(error.message, 'error'); }}
      finally {{ busy = false; }}
    }}
    function selectedEvidence(role) {{
      return [...document.querySelectorAll(`#evidence-${{role}} input:checked`)].map(input => input.value);
    }}
    async function save(moveNext) {{
      if (busy) return;
      const selectedLabel = document.querySelector('input[name="label"]:checked');
      const rationale = document.getElementById('rationale').value.trim();
      if (!selectedLabel) return setStatus('Tick one relationship label.', 'error');
      if (!selectedEvidence('a').length || !selectedEvidence('b').length) return setStatus('Tick evidence from both papers.', 'error');
      if (!rationale) return setStatus('Write a brief rationale.', 'error');
      busy = true;
      setStatus('Saving…');
      try {{
        const response = await fetch(`${{base}}api/presentation/${{current}}`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{label: Number(selectedLabel.value), rationale, evidence: {{a: selectedEvidence('a'), b: selectedEvidence('b')}}}}),
        }});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not save this answer.');
        dirty = false;
        if (moveNext && current + 1 < total) {{ busy = false; await load(current + 1); }}
        else {{
          document.getElementById('completed').textContent = `${{result.completed}} completed`;
          document.getElementById('progress').style.width = `${{(result.completed / result.total) * 100}}%`;
          setStatus(current + 1 === total ? 'Final answer saved' : 'Saved', 'saved');
        }}
      }} catch (error) {{ setStatus(error.message, 'error'); }}
      finally {{ busy = false; }}
    }}
    rubricInputs.forEach(input => input.addEventListener('change', markDirty));
    document.getElementById('rationale').addEventListener('input', markDirty);
    document.getElementById('back').addEventListener('click', () => {{
      if (!dirty || window.confirm('Discard unsaved changes and go back?')) load(current - 1);
    }});
    document.getElementById('save').addEventListener('click', () => save(false));
    document.getElementById('save-next').addEventListener('click', () => save(true));
    window.addEventListener('beforeunload', event => {{ if (dirty) {{ event.preventDefault(); event.returnValue = ''; }} }});
    load(0);
  </script>
</body>
</html>
""".encode("utf-8")


def create_server(
    *, session: ReviewSession, token: str, port: int = 0
) -> ThreadingHTTPServer:
    page = _page(token)
    page_path = f"/{token}/"
    api_prefix = f"/{token}/api/presentation/"
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{token}'; style-src 'nonce-{token}'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "AzothReviewer/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", csp)
            self.end_headers()

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def _index(self) -> int | None:
            path = urlsplit(self.path).path
            if not path.startswith(api_prefix):
                return None
            suffix = path[len(api_prefix) :]
            return int(suffix) if suffix.isdigit() else None

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == page_path:
                self._headers(200, "text/html; charset=utf-8", len(page))
                self.wfile.write(page)
                return
            index = self._index()
            if index is None:
                self._json(404, {"error": "not found"})
                return
            try:
                self._json(200, session.presentation(index))
            except ReviewerError as exc:
                self._json(400, {"error": str(exc)})
            except Exception:
                self._json(500, {"error": "reviewer request failed"})

        def do_POST(self) -> None:
            index = self._index()
            if index is None:
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._json(400, {"error": "invalid request body"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                self._json(400, {"error": "invalid request body"})
                return
            try:
                result = session.save_answer(
                    index,
                    label=payload.get("label"),
                    rationale=payload.get("rationale"),
                    evidence=payload.get("evidence"),
                )
                self._json(200, result)
            except ReviewerError as exc:
                self._json(400, {"error": str(exc)})
            except Exception:
                self._json(500, {"error": "reviewer request failed"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the private P5 adjudication reviewer")
    parser.add_argument("--private-gold", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if not 0 <= arguments.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    try:
        session = ReviewSession.open(
            packet_path=arguments.private_gold,
            source_dir=arguments.source_dir,
            benchmark_root=arguments.benchmark_root,
            repo_root=arguments.repo_root,
        )
    except ReviewerError as exc:
        raise SystemExit(f"Reviewer startup failed: {exc}") from None
    token = secrets.token_urlsafe(24)
    server = create_server(session=session, token=token, port=arguments.port)
    host, port = server.server_address
    url = f"http://{host}:{port}/{token}/"
    print(f"Azoth reviewer ready: {url}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    if arguments.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
