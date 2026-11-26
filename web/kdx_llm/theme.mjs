// KDX LLM - look shared with KDX Console: KDX blue accent + light/dark tokens.
//
// Same accent and tokens as ComfyUI-KDX-Console/web/kdx_console/theme.mjs, but every
// class here is prefixed `kdxl-` so the two packs never restyle each other's elements.
// Light or dark: compare the luminance of the page background with the page text (as
// Pixaroma's light_theme.mjs); the result is the shared `html.kdx-light` class, which
// both packs compute the same way. Default is dark.
// (.mjs on purpose: ComfyUI auto-loads only *.js from WEB_DIRECTORY.)

export const ACCENT = {
  dark: { acc: "#6f8dff", onAcc: "#060b1f", accText: "#9bb0ff" },
  light: { acc: "#2f4fd1", onAcc: "#ffffff", accText: "#2742b0" },
};

const CSS = `
.kdxl-root{--kdx-acc:${ACCENT.dark.acc};--kdx-on-acc:${ACCENT.dark.onAcc};--kdx-acc-text:${ACCENT.dark.accText};
 --kdx-bg:#1b1e21;--kdx-card:#23272b;--kdx-fg:#e7e9ea;--kdx-muted:#9aa1a7;--kdx-border:#363c42;
 --kdx-off-bg:#2b3035;--kdx-off-fg:#8b9298;--kdx-warn:#f0b429;--kdx-err:#ff6b6b;--kdx-field:#15181a;
 font:12px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--kdx-fg);box-sizing:border-box}
html.kdx-light .kdxl-root{--kdx-acc:${ACCENT.light.acc};--kdx-on-acc:${ACCENT.light.onAcc};--kdx-acc-text:${ACCENT.light.accText};
 --kdx-bg:#f6f7f6;--kdx-card:#ffffff;--kdx-fg:#1d211f;--kdx-muted:#4f5752;--kdx-border:#c9d0cb;
 --kdx-off-bg:#eceeed;--kdx-off-fg:#5e6661;--kdx-warn:#8a5a00;--kdx-err:#b3261e;--kdx-field:#ffffff}
.kdxl-root *{box-sizing:border-box}

.kdxl-toasts{position:fixed;right:24px;bottom:24px;z-index:99999;display:flex;flex-direction:column;align-items:flex-end;gap:6px;
 pointer-events:none;background:none;max-width:calc(100vw - 48px)}
.kdxl-toast{max-width:520px;white-space:pre-wrap;pointer-events:auto;
 background:var(--kdx-card);border:1px solid var(--kdx-border);border-left:3px solid var(--kdx-acc);border-radius:8px;
 padding:7px 12px;box-shadow:0 10px 30px rgba(0,0,0,.35);transition:opacity .3s ease}
.kdxl-toast.err{border-left-color:var(--kdx-err)}
.kdxl-toast.hide{opacity:0}

.kdxl-pop{position:fixed;z-index:99999;min-width:320px;max-width:560px;max-height:340px;display:flex;flex-direction:column;
 background:var(--kdx-bg);border:1px solid var(--kdx-border);border-radius:10px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.45)}
.kdxl-pop-head{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--kdx-card);
 border-bottom:2px solid var(--kdx-acc);font-weight:600}
.kdxl-pop-head .kdxl-count{margin-left:auto;color:var(--kdx-muted);font-weight:400}
.kdxl-pop-list{overflow:auto;padding:4px 0}
.kdxl-pop-empty{padding:10px 12px;color:var(--kdx-muted)}
.kdxl-pop-row{display:flex;align-items:center;gap:8px;width:100%;appearance:none;border:0;border-left:3px solid transparent;
 background:transparent;color:var(--kdx-fg);font:inherit;text-align:left;padding:6px 12px 6px 9px;cursor:pointer}
.kdxl-pop-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kdxl-pop-row:hover,.kdxl-pop-row:focus-visible{background:var(--kdx-off-bg);border-left-color:var(--kdx-acc);outline:none}
.kdxl-pop-row .kdxl-sub{margin-left:auto;color:var(--kdx-muted);flex:none}

.kdxl-dot{width:9px;height:9px;border-radius:50%;flex:none;background:var(--kdx-border)}
.kdxl-dot.loaded{background:var(--kdx-acc)}
.kdxl-dot.loading,.kdxl-dot.downloading{background:var(--kdx-warn)}
.kdxl-dot.failed{background:var(--kdx-err)}
.kdxl-dot.sleeping{background:var(--kdx-muted)}

textarea.kdxl-root.kdxl-answer{background:var(--kdx-field);color:var(--kdx-fg);border:1px solid var(--kdx-border);
 border-left:3px solid var(--kdx-acc);border-radius:6px;padding:6px 8px;user-select:text}
textarea.kdxl-root.kdxl-answer::placeholder{color:var(--kdx-muted)}
textarea.kdxl-root.kdxl-answer.pass{border-left-color:var(--kdx-warn)}
@media (prefers-reduced-motion:reduce){.kdxl-toast{transition:none}}
`;

let injected = false;

// Canvas buttons have no DOM element to anchor a popup to: open it at the last click.
let lastPointer = null;
document.addEventListener("pointerdown", (e) => { lastPointer = { x: e.clientX, y: e.clientY }; },
  { capture: true, passive: true });

function luminance(color) {
  const m = String(color).match(/\d+(\.\d+)?/g);
  if (!m || m.length < 3) return null;
  const [r, g, b] = m.slice(0, 3).map((v) => {
    const c = Number(v) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function detectLight() {
  try {
    const cs = getComputedStyle(document.body);
    const bg = luminance(cs.backgroundColor);
    const fg = luminance(cs.color);
    const light = bg != null && fg != null && bg > fg;
    document.documentElement.classList.toggle("kdx-light", light);
  } catch (_e) { /* keep dark */ }
}

export function ensureTheme() {
  if (injected) return;
  injected = true;
  const st = document.createElement("style");
  st.id = "kdx-llm-style";
  st.textContent = CSS;
  document.head.appendChild(st);
  detectLight();
  // ComfyUI rewrites the palette as inline style on <html> when the theme changes.
  new MutationObserver(() => detectLight()).observe(document.documentElement, {
    attributes: true, attributeFilter: ["style"],
  });
}

// ------------------------------------------------------------------ components

export function toast(msg, ok = true) {
  ensureTheme();
  const el = document.createElement("div");
  el.className = `kdxl-root kdxl-toast${ok ? "" : " err"}`;
  el.setAttribute("role", ok ? "status" : "alert");
  el.textContent = msg;
  let stack = document.getElementById("kdxl-toasts");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "kdxl-toasts";
    stack.className = "kdxl-root kdxl-toasts";
    document.body.appendChild(stack);
  }
  stack.appendChild(el);
  setTimeout(() => { el.classList.add("hide"); setTimeout(() => el.remove(), 350); }, ok ? 3000 : 5000);
}

/**
 * Floating pick list (models, saved sessions).
 * items: [{ value, label, title?, status?, sub? }]; `status` draws a coloured dot.
 */
export function showPicker({ id, title, items, empty, anchorEl, onSelect }) {
  ensureTheme();
  document.getElementById(id)?.remove();
  const pop = document.createElement("div");
  pop.id = id;
  pop.className = "kdxl-root kdxl-pop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", title);
  let rect = lastPointer ? { bottom: lastPointer.y, left: lastPointer.x } : { bottom: 200, left: 200 };
  if (anchorEl?.isConnected && typeof anchorEl.getBoundingClientRect === "function") {
    const r = anchorEl.getBoundingClientRect();
    if (r.width || r.height) rect = r;
  }
  Object.assign(pop.style, {
    top: `${Math.max(16, Math.min(rect.bottom + 2, window.innerHeight - 356))}px`,
    left: `${Math.max(16, Math.min(rect.left, window.innerWidth - 436))}px`,
  });

  const head = document.createElement("div");
  head.className = "kdxl-pop-head";
  const name = document.createElement("span");
  name.textContent = title;
  const count = document.createElement("span");
  count.className = "kdxl-count";
  count.textContent = String(items.length);
  head.append(name, count);

  const list = document.createElement("div");
  list.className = "kdxl-pop-list";
  if (!items.length) {
    const e = document.createElement("div");
    e.className = "kdxl-pop-empty";
    e.textContent = empty;
    list.appendChild(e);
  }

  const close = () => {
    pop.remove();
    document.removeEventListener("pointerdown", outside, true);
    document.removeEventListener("keydown", onKey, true);
  };
  const outside = (e) => { if (!pop.contains(e.target)) close(); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };

  for (const item of items) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "kdxl-pop-row";
    if (item.title) row.title = item.title;
    if (item.status !== undefined) {
      const dot = document.createElement("i");
      dot.className = `kdxl-dot ${item.status || ""}`;
      dot.setAttribute("aria-hidden", "true");
      row.appendChild(dot);
    }
    const label = document.createElement("span");
    label.textContent = item.label;
    row.appendChild(label);
    if (item.sub) {
      const sub = document.createElement("span");
      sub.className = "kdxl-sub";
      sub.textContent = item.sub;
      row.appendChild(sub);
    }
    row.addEventListener("click", () => { close(); onSelect(item.value); });
    list.appendChild(row);
  }

  pop.append(head, list);
  document.body.appendChild(pop);
  list.querySelector("button")?.focus({ preventScroll: true });
  setTimeout(() => {
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", onKey, true);
  }, 0);
}
