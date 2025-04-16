# Security Policy

## ✅ Overview

This project interacts with cloud services (e.g. AWS Bedrock, Twitter API), and therefore requires responsible handling of authentication credentials, API keys, and personal access tokens.

---

## 🔑 Secret Management

### Do NOT Commit Secrets
Ensure `.env`, `venv/`, and `*.key` files are included in `.gitignore`.  
Use `.env.example` for safe template sharing.

### Recommended Storage
- **Local testing**: `.env` (stored in project root, ignored by Git)
- **Production**: Use **AWS Secrets Manager** or **Parameter Store**

---

## 🧹 Git Cleanup

### If secrets were committed:
1. Use [`bfg-repo-cleaner`](https://rtyley.github.io/bfg-repo-cleaner/)
2. Run:
   ```
   java -jar bfg.jar --delete-files .env --no-blob-protection
   ```
3. Rotate your AWS keys immediately.
4. Force push after verification.

---

## 🛡 GitHub Push Protection

This repo uses **GitHub’s Secret Scanning + Push Protection**.  
Pushes will be rejected if they contain:
- AWS Access Keys
- Bearer tokens
- Any token-like strings resembling secrets

---

## 🆘 Incident Response

If you suspect a key leak:
- Rotate your keys at the provider (AWS Console → IAM → Access keys)
- Open an issue with `[SECURITY]` in the title (if applicable)
- Notify the repository maintainer privately (via GitHub profile)

---

### 🤝 Credits

Built with contributions from the open-source security and cloud community.
