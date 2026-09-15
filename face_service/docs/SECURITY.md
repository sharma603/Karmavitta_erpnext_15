# SECURITY

- API key required on recognition endpoints
- Payload size limits
- Content-type checks
- In-process rate limiting
- Never log images, embeddings, or API keys
- Company-scoped templates supplied by ERPNext (service does not query ERP DB)
- Duplicate failures never reveal the other employee ID

Use HTTPS in production (reverse proxy: nginx / Caddy).

Service-to-service: ERPNext stores Face Service URL + API key in Face Attendance Settings (Password field).
