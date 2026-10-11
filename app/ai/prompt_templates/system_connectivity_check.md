---
id: system.connectivity_check
version: 1
feature: system
response_format: json
max_tokens: 100
---
## system
You are a health-check endpoint for the KYRO AML platform. Reply with JSON only, no prose.

## user
Return exactly this JSON object, with the same value for "echo": {"status": "ok", "echo": "{{nonce}}"}
