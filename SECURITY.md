# Security Policy

## Credential Storage

OnlineSub treats user API keys and authentication tokens with paramount security:
- **Windows Credential Manager**: All credentials (Google Gemini, Cloudflare, Hugging Face) are stored in the OS-managed secure credential store via the Windows DPAPI/Credential API.
- **Zero Plaintext Persistence**: API keys are NEVER written to non-sensitive configuration files (`settings.json`), SQLite databases (`onlinesub.db`), crash dumps, or log files.
- **Redaction**: All exceptions, error messages, and network URLs are automatically sanitized through `CredentialManager.sanitize_text` to prevent accidental credential leakage in application logs.
- **HTTPS Enforcement**: All remote API communications are strictly encrypted using HTTPS.

## Reporting a Vulnerability

If you discover a security flaw or secret leakage issue, please contact the repository owner directly.
