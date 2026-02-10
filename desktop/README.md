# Desktop Client Roadmap

Future client can be built with Electron or Tauri and call the same API endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /projects`
- `POST /audits/start`
- `GET /audits/{id}/status`
- `GET /audits/{id}/results`
- `GET /projects/{id}/history`
- `GET /projects/{id}/actions`
- `GET /audits/{id}/report.pdf`
- `POST /schedules`
- `GET /schedules`

Recommended flow:

1. User pastes URL and starts audit.
2. Desktop client polls status endpoint.
3. Results are rendered offline-friendly and can be exported to PDF.
