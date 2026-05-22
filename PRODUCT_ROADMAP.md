# Agentheim Code — GUI-First Product Roadmap

> Goal: Transform from a developer-centric CLI tool into a consumer-friendly, GUI-first coding assistant that non-technical users can install, set up, and use intuitively.

## Research Synthesis

### What Leading Tools Do Right

| Tool | Install | Provider Setup | Model Selection | Onboarding |
|------|---------|---------------|-----------------|------------|
| **Cursor** | One-liner curl | Settings → Models → Paste key | Dropdown in chat | Implicit (just works) |
| **Continue.dev** | VS Code extension | YAML config + env vars | Dropdown with roles | Config-first, minimal UI |
| **VS Code Copilot BYOK** | Built-in | "Manage Language Models" wizard | Picker with provider icons | Guided add-model flow |
| **OpenRouter** | API key only | Single key = 100s of models | Model browser with filters | Simple dashboard |
| **Ollama** | Single binary | `ollama pull` CLI | Auto-detected locally | Very simple, local-first |

### Key Patterns
1. **Provider cards/tiles** — visual selection of provider type (OpenAI, Azure, Google, etc.)
2. **Per-provider forms** — each provider has unique fields (API key vs endpoint vs region)
3. **Test connection button** — validate before saving
4. **Model picker near chat** — always visible, one-click switch
5. **Secure key storage** — never show keys in UI, use OS keychain or env vars
6. **Recent projects** — open a folder, it remembers
7. **Welcome/onboarding screen** — first-launch guided setup

---

## Phase 1: Provider Setup Wizard (Foundation)

**Deliverable:** Users can add, edit, and test providers entirely through the web UI without touching CLI or config files.

### Backend
- `POST /api/providers` — create a new provider profile
- `GET /api/providers` — list configured profiles
- `DELETE /api/providers/{id}` — remove a profile
- `POST /api/providers/{id}/test` — test connection
- Provider templates with per-provider field schemas

### Frontend
- "Add Provider" button in Settings
- Provider type selector (cards for OpenAI, Azure, AWS, Google, OCI, OpenRouter, Ollama, Custom)
- Dynamic form based on provider type
- Test connection with loading spinner
- Save/Cancel flow
- Provider list with edit/delete actions

### Supported Providers & Fields

| Provider | Fields | Auth Mode |
|----------|--------|-----------|
| **OpenAI** | API Key | Bearer token |
| **Azure OpenAI** | Endpoint, Deployment, API Key | Azure key |
| **AWS Bedrock** | Region, Access Key, Secret Key | AWS credentials |
| **Google (Vertex)** | Project ID, Location, ADC or API Key | ADC / API key |
| **OCI GenAI** | Tenancy, Compartment, User, Fingerprint, Key File | API signing |
| **OpenRouter** | API Key | Bearer token |
| **Ollama** | Host URL (default: localhost:11434) | No auth |
| **Custom** | Name, Base URL, API Key, Model ID | Bearer token |

---

## Phase 2: First-Launch Onboarding

**Deliverable:** A new user installs Agentheim Code, opens it, and within 60 seconds has a working provider and workspace.

### Flow
1. **Welcome screen** — logo, tagline, "Get Started" button
2. **Workspace picker** — browse folders, recent projects, drag & drop
3. **Provider setup** — "You need an AI provider to get started"
   - Option A: "I have an API key" → provider wizard
   - Option B: "Use local models (Ollama)" → detect/install Ollama
   - Option C: "I'll set this up later" → skip with placeholder
4. **Test & confirm** — quick "Hello" test message to verify provider
5. **Done screen** — "You're ready!" with tips

---

## Phase 3: Installer & Distribution

**Deliverable:** Single-file installer, no prerequisites.

### Windows
- NSIS `.exe` installer (already building)
- Bundle Python runtime (via PyInstaller or embed)
- Or: pip install + create shortcuts
- Auto-updater via Tauri updater

### macOS
- `.dmg` with drag-to-Applications
- Code signing (future)

### Linux
- `.AppImage` or `.deb`

---

## Phase 4: UI Polish for Non-Technical Users

**Deliverable:** Every part of the UI is understandable without reading docs.

- **Welcome/Landing page** — recent projects, "Open folder", create new project
- **Model selector** — provider icon + model name + capability badges
- **Trust mode** — visual toggle with tooltips (Safe / Ask / Full)
- **Chat area** — message bubbles, syntax highlighting, copy buttons
- **File explorer** — tree view with icons, click to open in inspector
- **Approval queue** — card-based approvals with clear Accept/Deny buttons
- **Terminal output** — collapsible panels, copy button, clear formatting
- **Error handling** — toast notifications, friendly error messages
- **Loading states** — "Thinking...", "Writing files...", "Running tests..."
- **Empty states** — "No sessions yet. Start by asking a question."
- **Tooltips** — every icon and control has a tooltip

---

## Phase 5: Documentation for End Users

**Deliverable:** A non-technical person can set up and use the product without developer help.

- Rewrite `README.md` for end users (not developers)
- `GETTING_STARTED.md` — step-by-step with screenshots
- `PROVIDERS.md` — how to get API keys for each provider
- In-app help panel
- Video/gif demonstrations (future)

---

## Execution Order

1. **Provider wizard backend** (API + validation)
2. **Provider wizard frontend** (React components)
3. **Onboarding flow** (welcome → workspace → provider → done)
4. **Landing page redesign** (recent projects, open folder)
5. **Model selector redesign** (provider icons, info)
6. **UI polish pass** (tooltips, empty states, toasts)
7. **Installer improvements**
8. **Docs rewrite**
