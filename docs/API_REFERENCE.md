# API Reference

The local backend reuses the shared Agentheim Coder API.

Important routes:

- `GET /api/health`
- `GET /api/coder/sessions`
- `POST /api/coder/sessions`
- `GET /api/coder/sessions/{id}`
- `POST /api/coder/sessions/{id}/messages`
- `POST /api/coder/sessions/{id}/cancel`
- `GET /api/coder/models`
- `GET /api/coder/commands`
- `PATCH /api/coder/sessions/{id}/model`
- `PATCH /api/coder/sessions/{id}/mode`
- `GET /api/coder/files`
- `GET /api/coder/sessions/{id}/diff`

The backend binds to `127.0.0.1` by default.

