import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
import { ensureTheme, showPicker, toast } from "./kdx_llm/theme.mjs?v=0.10.5";

// ── Node colours by role (LiteGraph's built-in palette values) ──────
// Applied only to freshly created nodes; a colour the user picked is kept,
// because a saved workflow's colour is restored after nodeCreated runs.
const ROLE_COLORS = {
    connection: { color: "#223", bgcolor: "#335" },       // blue
    settings:   { color: "#323", bgcolor: "#535" },       // purple
    prompt:     { color: "#232", bgcolor: "#353" },       // green
    chat:       { color: "#233", bgcolor: "#355" },       // cyan
    output:     { color: "#2a363b", bgcolor: "#3f5159" }, // pale blue
};
const NODE_ROLES = {
    KDX_LLM_Client: "connection", KDX_LLM_Model_Profile: "connection", KDX_LLM_Diagnostics: "connection",
    KDX_LLM_Simple_Sampling: "settings", KDX_LLM_Options_Values: "settings", KDX_LLM_Advanced_Sampling: "settings",
    KDX_LLM_Quick_Presets: "settings", KDX_LLM_Media_Settings: "settings", KDX_LLM_Tool: "settings",
    KDX_LLM_System_Prompt: "prompt", KDX_LLM_User_Prompt: "prompt", KDX_LLM_Prompt_Template: "prompt",
    KDX_LLM_JSON_Output_Format: "prompt",
    KDX_LLM_Chat: "chat", KDX_LLM_Session: "chat",
    KDX_LLM_JSON_Extract: "output", KDX_LLM_JSON_Fields: "output",
    KDX_LLM_Response_Formatter: "output", KDX_LLM_Stats: "output",
};

async function postJson(path, body) {
    const response = await api.fetchApi(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    let data;
    try { data = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
    if (!response.ok && !data.error) throw new Error(`HTTP ${response.status}`);
    return data;
}

async function fetchModels(config) { return postJson("/kdx_llm/models", config); }
async function doLoad(config)      { return postJson("/kdx_llm/load", config); }
async function doUnload(config)    { return postJson("/kdx_llm/unload", config); }
async function fetchProfiles(model) {
    const response = await api.fetchApi(`/kdx_llm/profiles?model=${encodeURIComponent(model || "")}`);
    let data;
    try { data = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
    return data;
}

function getWidget(node, name) { return node.widgets?.find(w => w.name === name); }

function sanitizeComboWidget(node, name, fallback) {
    const w = getWidget(node, name);
    if (!w) return;
    if (name === "json_mode" && typeof w.value === "boolean") {
        w.value = w.value ? "on" : "off";
    }
    const options = w.options?.values || [];
    if (options.length) {
        if (!options.includes(w.value)) {
            w.value = options.includes(fallback) ? fallback : options[0];
        }
    } else if (w.value === "" || w.value === null || w.value === undefined) {
        w.value = fallback;
    }
}

function sanitizeIntWidget(node, name, fallback) {
    const w = getWidget(node, name);
    if (!w) return;
    const optionDefault = Number(w.options?.default);
    const def = Number.isFinite(optionDefault) ? optionDefault : fallback;
    if (w.value === "" || w.value === null || w.value === undefined || !Number.isFinite(Number(w.value))) {
        w.value = def;
    } else {
        w.value = Number(w.value);
    }
}

function sanitizeGraphChatNodes(app) {
    const nodes = app?.graph?._nodes || app?.graph?.nodes || [];
    for (const node of nodes) sanitizeChatNode(node);
}

function sanitizeChatNode(node) {
    if (!node || node.comfyClass !== "KDX_LLM_Chat") return;
    sanitizeComboWidget(node, "model_preset", "generic");
    sanitizeComboWidget(node, "thinking", "auto");
    sanitizeComboWidget(node, "json_mode", "auto");
    sanitizeComboWidget(node, "token_counter", "heuristic");
    sanitizeComboWidget(node, "history_media", "latest");
    const reasoning = getWidget(node, "reasoning_mode");
    if (reasoning && (reasoning.value === null || reasoning.value === undefined)) reasoning.value = "";
    sanitizeIntWidget(node, "load_timeout", 300);
    sanitizeIntWidget(node, "max_prompt_tokens", 0);
    sanitizeIntWidget(node, "max_history", 40);
    node.setDirtyCanvas?.(true, true);
}
function generateSessionId() { return "sess_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36); }

// ── Profile status polling manager ─────────────────────────────────
// Single setInterval for all KDX_LLM_Model_Profile nodes.
// Per-model cache with TTL, isPolling guard to prevent parallel fetches.
class ProfileStatusManager {
    constructor() {
        this._subscribers = new Map(); // nodeId -> { getModel, callback }
        this._cache = new Map();       // model -> { data, timestamp }
        this._interval = null;
        this._isPolling = false;
        this._ttl = 3000; // 3 seconds
    }

    subscribe(nodeId, getModel, callback) {
        this._subscribers.set(nodeId, { getModel, callback });
        this._startInterval();
    }

    unsubscribe(nodeId) {
        this._subscribers.delete(nodeId);
        if (this._subscribers.size === 0) this._stopInterval();
    }

    invalidate(model) {
        if (!model) return;
        this._cache.delete(model);
        if (!this._isPolling) {
            this._poll();
        }
    }

    _startInterval() {
        if (this._interval) return;
        this._interval = setInterval(() => this._poll(), 5000);
    }

    _stopInterval() {
        if (this._interval) {
            clearInterval(this._interval);
            this._interval = null;
        }
    }

    async _poll() {
        if (this._isPolling) return;
        const models = new Set();
        for (const sub of this._subscribers.values()) {
            const m = sub.getModel();
            if (m) models.add(m);
        }
        if (models.size === 0) return;

        this._isPolling = true;
        try {
            await Promise.all([...models].map(async (model) => {
                const cached = this._cache.get(model);
                if (cached && Date.now() - cached.timestamp < this._ttl) return;
                try {
                    const data = await fetchProfiles(model);
                    if (data.status === "ok") {
                        this._cache.set(model, { data, timestamp: Date.now() });
                    }
                } catch { /* ignore individual failures */ }
            }));
            // Notify subscribers
            for (const sub of this._subscribers.values()) {
                const m = sub.getModel();
                if (!m) continue;
                const entry = this._cache.get(m);
                if (entry) sub.callback(entry.data);
            }
        } finally {
            this._isPolling = false;
        }
    }
}

const statusManager = new ProfileStatusManager();

function setHidden(widget, hidden) {
    if (!widget) return;
    widget.hidden = hidden;
    if (widget.inputEl) widget.inputEl.style.display = hidden ? "none" : "";
    if (widget.el) widget.el.style.display = hidden ? "none" : "";
}

function updateDropdownFromAPI(widget, endpoint) {
    return async () => {
        try {
            const response = await api.fetchApi(endpoint);
            const data = await response.json();
            if (data.status !== "ok") throw new Error(data.error || "Profile lookup failed");
            const values = ["(none)", ...(data.profiles || []).filter(v => v !== "(none)")];
            widget.options = widget.options || {};
            widget.options.values = values;
            if (!values.includes(widget.value)) widget.value = values[0];
            widget.onChanged?.();
        } catch (error) {
            toast(`${endpoint} refresh failed: ${error.message}`, false);
        }
    };
}

// ── Chat: answer shown inside the node (live while streaming) ───────
const ANSWER_WIDGET = "answer";
const ANSWER_MIN_HEIGHT = 150;

function addAnswerWidget(node) {
    if (getWidget(node, ANSWER_WIDGET)) return;
    let widget;
    try {
        widget = ComfyWidgets.STRING(node, ANSWER_WIDGET, ["STRING", { multiline: true }], app).widget;
    } catch (e) {
        console.warn("[KDX] answer preview unavailable:", e);
        return;
    }
    widget.serialize = false;                                       // not saved in the workflow
    widget.options = { ...(widget.options || {}), serialize: false }; // not sent to the backend
    widget.options.getMinHeight = () => ANSWER_MIN_HEIGHT;            // room for a few lines
    widget.value = "";
    if (widget.inputEl) {
        ensureTheme();
        widget.inputEl.readOnly = true;
        widget.inputEl.placeholder = "The answer appears here when the node runs.";
        widget.inputEl.classList.add("kdxl-root", "kdxl-answer");
    }
}

const LLM_OFF_NOTE = "⏭ LLM off (llm_enabled = false): the prompt was passed on unchanged.";

function showAnswer(node, text, llmOff = false) {
    const widget = getWidget(node, ANSWER_WIDGET);
    if (!widget) return;
    widget.value = llmOff ? `${LLM_OFF_NOTE}\n\n${text || ""}` : (text || "");
    if (widget.inputEl) {
        widget.inputEl.value = widget.value;
        widget.inputEl.classList.toggle("pass", llmOff);
        widget.inputEl.title = llmOff ? LLM_OFF_NOTE : "";
        widget.inputEl.scrollTop = llmOff ? 0 : widget.inputEl.scrollHeight;
    }
    node.setDirtyCanvas?.(true, false);
}

api.addEventListener("kdx_llm.stream", ({ detail }) => {
    const id = Number(detail?.node);
    if (!Number.isFinite(id)) return;
    const node = app.graph?.getNodeById?.(id);
    if (!node || node.comfyClass !== "KDX_LLM_Chat") return;
    const text = detail.text || (detail.thinking ? `💭 ${detail.thinking}` : "");
    showAnswer(node, text);
});

// ── JSON Fields: label outputs with the field names ─────────────────
function relabelFieldOutputs(node, raw) {
    if (!node.outputs) return;
    const text = String(raw || "").trim();
    let lines = text ? text.split(/\r?\n/) : [];
    if (lines.length === 1 && !lines[0].includes(":")) lines = lines[0].split(",");
    const names = [];
    for (const line of lines) {
        const item = line.trim().replace(/^[-*•]\s*/, "");
        if (!item || item.startsWith("#")) continue;
        const name = item.split(":")[0].trim().replace(/^["']|["']$/g, "");
        if (name && !names.includes(name)) names.push(name);
    }
    for (let i = 0; i < 6; i++) {
        const out = node.outputs[i];
        if (out) out.label = names[i] || `field_${i + 1}`;
    }
    node.setDirtyCanvas?.(true, true);
}

// ── Node look: role colours ─────────────────────────────────────────
app.registerExtension({
    name: "KDX.LLMLook",
    nodeCreated(node) {
        const role = NODE_ROLES[node.comfyClass];
        if (!role || node.color || node.bgcolor) return;
        Object.assign(node, ROLE_COLORS[role]);
    },
});

// ── Node pack id (aux_id) repair ─────────────────────────────────────
// ComfyUI-Manager stamps nodes with properties.aux_id taken from the pack's
// git remote. With an SSH host alias (deploy keys) that is a URL such as
// "git@github-kdx:korodexios/ComfyUI-KDX-LLM", which the frontend rejects when
// a workflow is pasted or loaded ("Invalid aux_id: Must be valid
// 'github-username/github-repo-name'"). Rewrite such values to "owner/repo"
// (and drop anything unrecoverable) whenever a node is loaded or serialized.
const AUX_USER_RE = /^(?!-)(?!.*--)[a-zA-Z0-9-]{1,39}(?<!-)$/;
const AUX_REPO_RE = /^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?$/;

function isValidAuxId(value) {
    if (typeof value !== "string") return false;
    const parts = value.split("/");
    return parts.length === 2 && AUX_USER_RE.test(parts[0]) && AUX_REPO_RE.test(parts[1]);
}

function normalizeAuxId(value) {
    if (typeof value !== "string" || isValidAuxId(value)) return value;
    // git@host:owner/repo(.git) · ssh://git@host/owner/repo · https://host/owner/repo(.git)
    const match = value.trim().match(/[:/]([^/:@\s]+)\/([^/\s]+?)(?:\.git)?\/?$/);
    const candidate = match ? `${match[1]}/${match[2]}` : null;
    return isValidAuxId(candidate) ? candidate : undefined;
}

function repairAuxId(properties) {
    if (!properties || !("aux_id" in properties)) return;
    const fixed = normalizeAuxId(properties.aux_id);
    if (fixed === properties.aux_id) return;
    if (fixed === undefined) delete properties.aux_id;
    else properties.aux_id = fixed;
}

app.registerExtension({
    name: "KDX.AuxIdRepair",
    beforeRegisterNodeDef(nodeType) {
        // Every node type: a bad aux_id breaks pasting the whole selection.
        const origSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function(data) {
            const result = origSerialize?.apply(this, arguments);
            repairAuxId(data?.properties);
            return result;
        };
    },
    nodeCreated(node) { repairAuxId(node.properties); },
    loadedGraphNode(node) { repairAuxId(node.properties); },
});

// ── Client node: DUMB — just connection + model ───────────────────
app.registerExtension({
    name: "KDX.LLMClient",
    async nodeCreated(node) {
        if (node.comfyClass !== "KDX_LLM_Client") return;

        const config = () => ({
            url: getWidget(node, "base_url")?.value || "http://127.0.0.1:8080",
            api_key: getWidget(node, "api_key")?.value || "",
            api_key_env: getWidget(node, "api_key_env")?.value || "KDX_LLM_API_KEY",
            timeout: Number(getWidget(node, "timeout")?.value || 30),
            provider: getWidget(node, "provider")?.value || "auto",
        });

        node.addWidget("button", "📡 select model", "", async () => {
            try {
                const data = await fetchModels(config());
                if (data.status !== "ok") { toast(data.error || "Model discovery failed.", false); }
                else if (!data.models?.length) { toast("The server returned no models.", false); }
                else {
                    showPicker({
                        id: "kdx_picker",
                        title: "Models",
                        empty: "No models reported by the server.",
                        items: data.models.map((m) => ({
                            value: m.id,
                            label: m.id,
                            status: m.status || "unknown",
                            sub: m.status && m.status !== "unknown" ? m.status : "",
                            title: `${m.owned_by || "unknown"} • ${m.status || "unknown"}`,
                        })),
                        onSelect: (modelId) => {
                            const w = getWidget(node, "model");
                            if (w) { w.value = modelId; node.setDirtyCanvas(true, true); }
                            toast(`Selected: ${modelId}`);
                        },
                    });
                }
            } catch (e) { toast(`Model discovery failed: ${e.message}`, false); }
        }, { serialize: false });

        node.addWidget("button", "▶ load", "", async () => {
            const model = getWidget(node, "model")?.value?.trim();
            if (!model) { toast("Select a model first.", false); return; }
            try {
                const data = await doLoad({ ...config(), model, wait: true, wait_timeout: 300 });
                if (data.status === "ok") toast(`Loaded: ${model}`);
                else if (data.status === "unsupported") toast(data.detail || "Explicit loading is not supported.", false);
                else toast(data.detail || `Load status: ${data.status}`, false);
            } catch (e) { toast(`Load failed: ${e.message}`, false); }
        }, { serialize: false });

        node.addWidget("button", "⏹ unload", "", async () => {
            const model = getWidget(node, "model")?.value?.trim();
            if (!model) { toast("Select a model first.", false); return; }
            if (!confirm(`Unload "${model}"?`)) return;
            try {
                const data = await doUnload({ ...config(), model });
                if (data.status === "ok") toast(`Unloaded: ${model}`);
                else if (data.status === "unsupported") toast(data.detail || "Explicit unloading is not supported.", false);
                else toast(data.detail || `Unload status: ${data.status}`, false);
            } catch (e) { toast(`Unload failed: ${e.message}`, false); }
        }, { serialize: false });
    },
});

// ── UX extensions ──────────────────────────────────────────────────
app.registerExtension({
    name: "KDX.LLMUX",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "KDX_LLM_Chat") {
            const origConfigure = nodeType.prototype.configure;
            nodeType.prototype.configure = function(info) {
                const result = origConfigure?.apply(this, arguments);
                sanitizeChatNode(this);
                this._kdxUpdateAdvanced?.();
                return result;
            };
            const origExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function(message) {
                const result = origExecuted?.apply(this, arguments);
                const answer = message?.kdx_response?.[0];
                if (answer !== undefined) showAnswer(this, answer, message?.kdx_llm_off?.[0] === true);
                return result;
            };
        }
    },
    loadedGraphNode(node) {
        sanitizeChatNode(node);
    },
    afterConfigureGraph(missingNodeTypes, app) {
        sanitizeGraphChatNodes(app);
    },
    afterLoadGraph(app) {
        sanitizeGraphChatNodes(app);
    },
    async nodeCreated(node) {
        const w = (name) => getWidget(node, name);

        if (node.comfyClass === "KDX_LLM_Chat") {
            // Migrate old/empty Chat widget values after schema changes.
            sanitizeChatNode(node);

            // P1.4: V3 schema marks advanced fields natively (advanced=True). If
            // present, ComfyUI's native Advanced group handles show/hide — do NOT
            // add a competing custom toggle.
            const hasNativeAdvanced = node.widgets?.some(w => w.options?.advanced || w.advanced);

            if (!hasNativeAdvanced) {
                const advancedToggle = node.addWidget(
                    "toggle", "🔧 advanced", false, () => {},
                    { tooltip: "Show/hide advanced settings: streaming, media mode, history limits, JSON sampling, model load/unload." },
                );

                // Everyday controls stay visible (prompt, preset, thinking, reasoning,
                // system prompt, JSON mode, session); the rest lives behind the toggle.
                const advancedFields = [
                    "sampling_json_thinking", "sampling_json_non_thinking", "extra_request_json",
                    "load_before", "unload_after", "load_timeout", "max_prompt_tokens", "token_counter",
                    "stream", "media_mode", "max_history", "history_media",
                ];

                const updateAdvanced = () => {
                    const show = !!advancedToggle.value;
                    for (const name of advancedFields) setHidden(w(name), !show);
                    // reasoning_custom visible only when advanced AND reasoning_mode = custom
                    const rcWidget = w("reasoning_custom");
                    const rmWidget = w("reasoning_mode");
                    if (rcWidget && rmWidget) setHidden(rcWidget, !show || rmWidget.value !== "custom");
                    node.setDirtyCanvas(true, true);
                };
                advancedToggle.callback = updateAdvanced;
                // A saved workflow restores the toggle's value after nodeCreated;
                // configure() re-applies visibility through this hook.
                node._kdxUpdateAdvanced = updateAdvanced;

                // P1.4 bug fix: re-run updateAdvanced when reasoning_mode changes,
                // so reasoning_custom shows immediately when the user picks "custom"
                // (previously it only appeared after toggling 🔧 advanced off/on).
                const rmWidget = w("reasoning_mode");
                if (rmWidget) {
                    const origRmCallback = rmWidget.callback;
                    rmWidget.callback = function(val) {
                        origRmCallback?.apply(this, arguments);
                        updateAdvanced();
                    };
                }

                updateAdvanced();
            }

            const sessionIdWidget = w("session_id");
            if (sessionIdWidget) {
                node.addWidget("button", "🎲 new session", "", () => {
                    sessionIdWidget.value = generateSessionId();
                    w("reset_session").value = true;
                    toast(`New session: ${sessionIdWidget.value.substring(0, 15)}...`);
                }, { serialize: false });
            }

            addAnswerWidget(node);
            if (node.size) {
                node.size[0] = Math.max(360, Math.min(node.size[0], 430));
                // Fit the answer box on new nodes; a saved workflow restores its own size afterwards.
                const needed = node.computeSize?.()[1];
                if (needed && node.size[1] < needed) node.size[1] = needed;
            }
        }

        if (node.comfyClass === "KDX_LLM_JSON_Fields") {
            const fieldsWidget = w("fields");
            const relabel = () => relabelFieldOutputs(node, fieldsWidget?.value);
            if (fieldsWidget) {
                const orig = fieldsWidget.callback;
                fieldsWidget.callback = function(...args) {
                    const r = orig?.apply(this, args);
                    relabel();
                    return r;
                };
                fieldsWidget.inputEl?.addEventListener("input", relabel);
            }
            const origConfigure = node.onConfigure;
            node.onConfigure = function(...args) {
                const r = origConfigure?.apply(this, args);
                relabel();
                return r;
            };
            relabel();
        }

        if (node.comfyClass === "KDX_LLM_System_Prompt") {
            const profile = w("profile");
            const action = w("action");
            if (!profile) return;

            const doRefresh = updateDropdownFromAPI(profile, "/kdx_llm/prompts");
            node.addWidget("button", "↻ refresh", "", doRefresh, { serialize: false });

            const origCallback = action?.callback;
            action.callback = (value) => {
                origCallback?.(value);
                if (value === "save" || value === "delete") setTimeout(doRefresh, 2000);
            };
        }

        if (node.comfyClass === "KDX_LLM_User_Prompt") {
            const profile = w("profile");
            const action = w("action");
            if (!profile) return;

            const doRefresh = updateDropdownFromAPI(profile, "/kdx_llm/user-prompts");
            node.addWidget("button", "↻ refresh", "", doRefresh, { serialize: false });

            const origCallback = action?.callback;
            action.callback = (value) => {
                origCallback?.(value);
                if (value === "save" || value === "delete") setTimeout(doRefresh, 2000);
            };
        }

        // ── Session: saved session picker/delete helpers ──
        if (node.comfyClass === "KDX_LLM_Session") {
            const nameWidget = w("session_name");

            async function fetchSessions() {
                const response = await api.fetchApi("/kdx_llm/sessions");
                let data;
                try { data = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
                if (data.status !== "ok") throw new Error(data.error || "Session lookup failed.");
                return data.sessions || [];
            }

            if (nameWidget) {
                node.addWidget("button", "📂 saved sessions", "", async () => {
                    try {
                        const sessions = await fetchSessions();
                        showPicker({
                            id: "kdx_session_picker",
                            title: "Saved sessions",
                            empty: "No saved sessions.",
                            anchorEl: nameWidget.inputEl,
                            items: sessions.map((name) => ({ value: name, label: name })),
                            onSelect: (name) => {
                                nameWidget.value = name;
                                node.setDirtyCanvas(true, true);
                            },
                        });
                    } catch (e) {
                        toast(`Session list failed: ${e.message}`, false);
                    }
                }, { serialize: false });

                node.addWidget("button", "🗑 delete session", "", async () => {
                    const name = (nameWidget.value || "").trim();
                    if (!name) { toast("No session name set.", false); return; }
                    if (!confirm(`Delete saved session "${name}"?`)) return;
                    try {
                        const data = await postJson("/kdx_llm/sessions/delete", { name });
                        if (data.status === "ok") {
                            toast(`Deleted session "${name}".`, true);
                            nameWidget.value = "";
                            node.setDirtyCanvas(true, true);
                        } else if (data.status === "not_found") {
                            toast(`Session "${name}" was not found.`, false);
                        } else {
                            toast(data.error || "Delete failed.", false);
                        }
                    } catch (e) {
                        toast(`Delete failed: ${e.message}`, false);
                    }
                }, { serialize: false });
            }
        }

        // ── Model Profile: profile picker + save/delete + status ──
        if (node.comfyClass === "KDX_LLM_Model_Profile") {
            const profile = w("profile");
            let lastModel = null;

            function applyProfileOptions(model, data) {
                if (!profile || !model) return;
                const keys = new Set([model, "(none)"]);
                for (const p of data?.profiles || []) {
                    if (p?.key) keys.add(p.key);
                }
                const values = Array.from(keys).sort();
                profile.options = profile.options || {};
                profile.options.values = values;
                if (!values.includes(profile.value)) {
                    profile.value = values.includes(model) ? model : "(none)";
                }
                profile.onChanged?.();
                node.setDirtyCanvas(true, true);
            }

            // ── Graph helpers (correct LiteGraph API) ──
            // In current ComfyUI, graph.links is a Proxy-wrapped Map — use
            // node.getInputNode(slot) / node.getInputLink(slot) instead of
            // bracket access on graph.links.
            function getInputSlotIndex(inputName) {
                if (!node.inputs) return -1;
                return node.inputs.findIndex(i => i.name === inputName);
            }

            function getModelFromClient() {
                const idx = getInputSlotIndex("client");
                if (idx < 0) return "";
                let clientNode = node.getInputNode?.(idx);
                if (!clientNode) return "";
                // Client may also go through a Reroute
                clientNode = resolveSourceNode(clientNode);
                const modelWidget = clientNode?.widgets?.find(w => w.name === "model");
                return modelWidget?.value?.trim() || "";
            }

            // Read enabled sampling params from a connected Simple/Advanced node.
            // Handles Reroute nodes: if getInputNode() returns a Reroute,
            // follow its input link to the real source node.
            function resolveSourceNode(nodeObj) {
                let current = nodeObj;
                let hops = 0;
                while (current && hops < 10) {
                    const isReroute = current.comfyClass === "Reroute" || current.type === "Reroute";
                    if (!isReroute) break;
                    const upstream = current.getInputNode?.(0);
                    if (!upstream || upstream === nodeObj) break;
                    current = upstream;
                    hops++;
                }
                return current;
            }

            const SIMPLE_SAMPLING_KEYS = new Set([
                "temperature", "top_p", "top_k", "min_p",
                "repeat_penalty", "presence_penalty", "frequency_penalty",
                "max_tokens", "seed",
            ]);
            const ADVANCED_SAMPLING_KEYS = new Set([
                "n_ctx", "repeat_last_n", "thinking_budget",
                "mirostat", "mirostat_tau", "mirostat_eta",
            ]);

            async function fetchPresetParams(name) {
                const response = await api.fetchApi(`/kdx_llm/presets?name=${encodeURIComponent(name || "")}`);
                let data;
                try { data = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
                return data;
            }

            async function getConnectedSampling(inputName) {
                const idx = getInputSlotIndex(inputName);
                if (idx < 0) { return {}; }
                const connected = node.isInputConnected?.(idx);
                if (!connected) { return {}; }
                let srcNode = node.getInputNode?.(idx);
                if (!srcNode) { return {}; }
                // Resolve through Reroute nodes
                const resolved = resolveSourceNode(srcNode);
                srcNode = resolved;

                if (!srcNode?.widgets) { return {}; }

                const cls = srcNode.comfyClass || srcNode.type || "";
                const opts = {};

                if (cls === "KDX_LLM_Quick_Presets") {
                    const preset = srcNode.widgets.find(w => w.name === "preset")?.value;
                    if (!preset || preset === "(none)") return {};
                    try {
                        const data = await fetchPresetParams(preset);
                        if (data.status === "ok" && data.params && typeof data.params === "object") {
                            Object.assign(opts, data.params);
                        }
                    } catch (e) {
                        toast(`Quick preset lookup failed for "${preset}": ${e.message}`, false);
                    }
                    return opts;
                }

                const known = cls === "KDX_LLM_Advanced_Sampling" ? ADVANCED_SAMPLING_KEYS : SIMPLE_SAMPLING_KEYS;
                for (const w of srcNode.widgets) {
                    if (!known.has(w.name)) continue;
                    const enableW = srcNode.widgets.find(e => e.name === w.name + "_enabled");
                    if (enableW && !enableW.value) continue;
                    if (w.value !== undefined && w.value !== null && w.value !== "") {
                        opts[w.name] = w.value;
                    }
                }

                if (cls !== "KDX_LLM_Advanced_Sampling") {
                    const stopEnabled = srcNode.widgets.find(e => e.name === "stop_enabled");
                    const stopWidget = srcNode.widgets.find(e => e.name === "stop");
                    if (stopEnabled?.value && stopWidget?.value?.trim()) {
                        opts["stop"] = stopWidget.value.trim().split("\n").map(s => s.trim()).filter(Boolean);
                    }
                }

                if (cls === "KDX_LLM_Advanced_Sampling") {
                    const extraEnabled = srcNode.widgets.find(e => e.name === "extra_body_enabled");
                    const extraWidget = srcNode.widgets.find(e => e.name === "extra_body");
                    if (extraEnabled?.value && extraWidget?.value?.trim()) {
                        try {
                            const parsed = JSON.parse(extraWidget.value.trim());
                            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                                Object.assign(opts, parsed);
                            } else {
                                toast("Advanced Sampling extra_body must be a JSON object.", false);
                            }
                        } catch (e) {
                            toast(`Invalid extra_body JSON: ${e.message}`, false);
                        }
                    }
                }

                return opts;
            }

            // 📂 refresh profile dropdown from server (filtered by model)
            if (profile) {
                const doRefresh = async () => {
                    try {
                        const model = getModelFromClient();
                        const data = await fetchProfiles(model);
                        if (data.status !== "ok") { toast(data.error || "Profile lookup failed.", false); return; }
                        // Always include model ID as fallback option
                        const keys = new Set();
                        if (model) keys.add(model);
                        for (const p of data.profiles || []) keys.add(p.key);
                        keys.add("(none)");
                        const values = Array.from(keys).sort();
                        profile.options = profile.options || {};
                        profile.options.values = values;
                        if (!values.includes(profile.value)) profile.value = values.includes(model) ? model : "(none)";
                        applyProfileOptions(model, data);
                        lastModel = model;
                        statusManager.invalidate(model);
                    } catch (e) { toast(`Profile refresh failed: ${e.message}`, false); }
                };
                node.addWidget("button", "↻ refresh profiles", "", doRefresh, { serialize: false });
            }

            // 💾 save profile — direct API call (no node queue needed)
            if (profile) {
                node.addWidget("button", "💾 save", "", async () => {
                    const model = getModelFromClient();
                    if (!model) { toast("No model selected — connect a Client node first.", false); return; }
                    const suffix = (w("profile_name")?.value || "").trim();
                    // Key = model ID + optional suffix (e.g. "model-test")
                    const key = suffix ? `${model}-${suffix}` : model;

                    const think = await getConnectedSampling("thinking_options");
                    const nonthink = await getConnectedSampling("non_thinking_options");
                    const advanced = w("advanced")?.value || false;
                    const trj = advanced ? (w("thinking_request_json")?.value || "") : "";
                    const nrj = advanced ? (w("non_thinking_request_json")?.value || "") : "";

                    if (!Object.keys(think).length && !Object.keys(nonthink).length) {
                        toast("No sampling nodes connected — nothing to save.\nConnect a Simple/Advanced Sampling or Quick Presets node to thinking_options or non_thinking_options.", false);
                        return;
                    }

                    try {
                        const data = await postJson("/kdx_llm/profiles/save", {
                            model: model,
                            key: key,
                            profile: {
                                thinking: { sampling: think, request: { ...(trj ? JSON.parse(trj) : {}) } },
                                non_thinking: { sampling: nonthink, request: { ...(nrj ? JSON.parse(nrj) : {}) } },
                            },
                        });
                        if (data.status === "ok") {
                            toast(`Profile "${key}" saved (thinking: ${Object.keys(think).length} params, non-thinking: ${Object.keys(nonthink).length} params).`);
                            // Update dropdown to include the new key
                            if (suffix && profile.options?.values && !profile.options.values.includes(key)) {
                                profile.options.values.push(key);
                                profile.options.values.sort();
                            }
                            // Select the saved profile in dropdown
                            profile.value = key;
                            // Clear profile_name after successful save (it was for naming)
                            w("profile_name").value = "";
                            statusManager.invalidate(model);
                        }
                        else { toast(data.error || "Save failed.", false); }
                    } catch (e) { toast(`Save failed: ${e.message}`, false); }
                }, { serialize: false });
            }

            // 🗑 delete profile — direct API call
            if (profile) {
                node.addWidget("button", "🗑 delete", "", async () => {
                    const current = profile.value;
                    if (current === "(none)" || !current) { toast("No profile selected.", false); return; }
                    if (!confirm(`Delete profile "${current}"?`)) return;
                    try {
                        const data = await postJson("/kdx_llm/profiles/delete", { key: current });
                        if (data.status === "ok") {
                            toast(`Profile "${current}" deleted.`);
                            // Remove from dropdown values
                            if (profile.options?.values) {
                                const idx = profile.options.values.indexOf(current);
                                if (idx >= 0) profile.options.values.splice(idx, 1);
                            }
                            // Reset dropdown to model ID
                            const model = getModelFromClient();
                            profile.value = model || "(none)";
                            statusManager.invalidate(model);
                        }
                        else { toast(data.error || "Delete failed.", false); }
                    } catch (e) { toast(`Delete failed: ${e.message}`, false); }
                }, { serialize: false });
            }

            // ── Status: show which profile is loaded ──
            // P1.4: native LiteGraph text widget (no floating DOM overlay, no
            // zoom/pan/minimize overlap). serialize:false keeps it out of the
            // workflow JSON and the Python backend payload.
            const statusWidget = node.addWidget(
                "text", "status", "(no model connected)", () => {},
                { serialize: false, tooltip: "Profile auto-load status." },
            );
            statusWidget.disabled = true; // LiteGraph native read-only flag
            if (statusWidget.inputEl) {
                statusWidget.inputEl.readOnly = true;
                statusWidget.inputEl.style.opacity = "0.75";
                statusWidget.inputEl.style.textAlign = "center";
                statusWidget.inputEl.style.cursor = "default";
                statusWidget.inputEl.style.fontStyle = "italic";
                statusWidget.inputEl.style.fontSize = "10px";
            }

            function handleStatusUpdate(data) {
                let text = "(no profile — server defaults)";
                if (data.status === "no_model") {
                    text = "(no model connected)";
                } else if (data.status === "ok" && data.profiles?.length) {
                    const exact = data.profiles.find(p => !p.is_glob);
                    const glob = data.profiles.find(p => p.is_glob);
                    const match = exact || glob;
                    if (match) text = `📋 ${match.key} (auto-loaded)`;
                }
                statusWidget.value = text;
                node.setDirtyCanvas(true, true);

                const model = getModelFromClient();
                if (model && model !== lastModel) {
                    lastModel = model;
                    applyProfileOptions(model, data);
                }
            }

            // Subscribe to the shared polling manager (replaces per-node setInterval)
            statusManager.subscribe(node.id, getModelFromClient, handleStatusUpdate);

            // Cleanup on node removal
            const origOnRemoved = node.onRemoved;
            node.onRemoved = function(...args) {
                statusManager.unsubscribe(node.id);
                if (origOnRemoved) origOnRemoved.apply(this, args);
            };

            // Invalidate cache after save/delete
            const origSaveBtn = node.widgets?.find(w => w.name === "💾 save");
            if (origSaveBtn) {
                const origSaveCallback = origSaveBtn.callback;
                origSaveBtn.callback = async function(...args) {
                    const result = await origSaveCallback?.apply(this, args);
                    const model = getModelFromClient();
                    if (model) statusManager.invalidate(model);
                    return result;
                };
            }
            const origDeleteBtn = node.widgets?.find(w => w.name === "🗑 delete");
            if (origDeleteBtn) {
                const origDeleteCallback = origDeleteBtn.callback;
                origDeleteBtn.callback = async function(...args) {
                    const result = await origDeleteCallback?.apply(this, args);
                    const model = getModelFromClient();
                    if (model) statusManager.invalidate(model);
                    return result;
                };
            }

            // Advanced toggle: show JSON overrides
            const advWidget = w("advanced");
            if (advWidget) {
                const update = () => {
                    const show = !!advWidget.value;
                    setHidden(w("thinking_request_json"), !show);
                    setHidden(w("non_thinking_request_json"), !show);
                    node.setDirtyCanvas(true, true);
                };
                advWidget.callback = update;
                update();
            }
        }
    },
});
