# SECURITY

- API key required on recognition endpoints
- Payload size limits
- Content-type checks
- In-process rate limiting
- Never log images, embeddings, or API keys
- Company-scoped templates supplied by ERPNext (service does not query ERP DB)
- Duplicate failures never reveal the other employee ID

Use HTTPS in production (reverse proxy: nginx / Caddy).

Frappe Cloud in-process mode handles inference inside the Frappe worker and needs no
service URL or service key. Optional external mode sends images over HTTPS and uses
the Face Service API Key stored in Face Attendance Settings (Password field).
