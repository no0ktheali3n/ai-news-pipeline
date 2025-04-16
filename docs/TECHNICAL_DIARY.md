# Technical Diary

This file documents major technical decisions, fixes, lessons learned, and recurring patterns.

---

## 🌱 Phase 1 – Scraper Foundation
- Created initial `scraper-alpha` using BeautifulSoup
- Defined target structure from arXiv.org advanced search
- Implemented random user agents and human-like delay via `random_delay()`
- Integrated basic pandas export to `.json`

### Lessons:
- arXiv structure is relatively stable but still needs tag inspection
- User-agent rotation helps avoid soft blocking and cloudflare

---

## 🧪 Phase 2 – Summarizer Evolution
- Integrated AWS Bedrock and Claude 3.5 (then tested 3.7)
- Hit throttling issues → resolved with retry + backoff logic
- Prompt v1 and v2 A/B testing implemented inside `summarizer.py`
- Token usage logging + character budgeting added
- Output schema enhanced with `summary_v1`, `summary_v2`, `hashtags`, etc.

### Challenges:
- Throttling required exponential retry handling (sensitive to backoff)
- AWS Bedrock doesn’t always fail predictably (JSON fallback logic needed)

---

## 🖋 Phase 3 – Poster Formatter
- `poster-lab.ipynb` created to format tweets with full trimming logic
- Added dynamic hashtag injection from summarizer output
- Found and fixed link formatting bug (double base URL)

---

## 🔐 Secrets Incident (2025-04-10)
- Accidentally committed AWS credentials to public repo
- GitHub Push Protection blocked push
- Used BFG Repo Cleaner and `git filter-repo` to purge Git history
- Added `.env.example` and full `.gitignore` enforcement

---
## 🖋 Phase 4 - Social Media Integration

## Tweepy development (2025-04-12)

Problems Encountered:
🧱 Initial 403/404 Forbidden error despite valid credentials.
🔍 Discovered missing app permissions (read/write not enabled).
🔐 OAuth 1.0a user context required — OAuth 2.0 not sufficient for tweeting.
🛠️ Misalignment between Twitter’s UI vs actual API capabilities caused confusion.

Solutions:
✔ Enabled read/write permissions in dev portal under project > app > settings.
✔ Regenerated OAuth 1.0a access tokens and added to .env.
✔ Used Tweepy’s Client.create_tweet() to verify tweet delivery.
✔ Confirmed success via printed tweet URL and live post check.

Recommendations:
🔒 Store sensitive tokens only in .env, commit .env.example instead.
🔁 Consider support for token rotation or Twitter app permissions audit as part of future hardening.
🧪 Use if __name__ == "__main__": block for standalone local tests on every module.

## 💡 Roadmap
- Migrate from `.env` to Secrets Manager for cloud usage
- Add Twitter/X Tweepy automation as optional Lambda trigger
- CI/CD automation via GitHub Actions + SAM deployment
- Add HuggingFace summarization fallback or multi-model support

**Technical Diary Entry: AWS IAM + SAM Deployment (v0.4.3)**

**Date:** 2025-04-15  
**Milestone:** First successful deployment of the full AI News Pipeline (Scraper, Summarizer, Poster) to AWS Lambda using SAM.

---

### 🏠 Objective
Deploy all three pipeline components to AWS Lambda via SAM CLI with proper IAM-based security, least privilege access, and environment validation. Ensure the project is production-ready for modular triggers and automation.

---

### ⚡ Problems & Challenges Faced

#### 1. **IAM User Group Setup**
- **Problem:** No predefined user structure. Unsure whether to assign permissions per user or group.
- **Solution:** Created two IAM groups:
  - `ai-pipeline-admin` — Full deployment, management, secrets, logs, and Bedrock access.
  - `ai-pipeline-contributor` — Read-only logs + minimal Bedrock invocation.
- **Outcome:** User permissions are now modular and easily assignable.

#### 2. **IAM Policy Incompleteness**
- **Problem:** Initial deployments failed due to missing permissions for `CreateRole`, `AttachRolePolicy`, etc.
- **Solution:** Expanded `ai-pipeline-admin-policy` to include:
  ```json
  "Action": [
    "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
    "iam:DeleteRole", "iam:DetachRolePolicy", "iam:DeleteRolePolicy",
    "iam:TagRole", "iam:UntagRole"
  ]
  ```
- **Outcome:** Full Lambda stack creation works as intended.

#### 3. **CloudWatch Log Access Confusion**
- **Problem:** Couldn’t locate `logs:ViewLogEvents`, permissions UI split by service (CloudWatch vs Logs).
- **Solution:** Found `logs:GetLogEvents` under the dedicated **Logs** service. Enabled in contributor and admin roles.
- **Lesson:** AWS UI separates CloudWatch metrics vs Logs permissions.

#### 4. **Environment Variable Conflicts (`AWS_REGION`)**
- **Problem:** CloudFormation rejected Lambda creation due to `AWS_REGION` being a reserved environment variable.
- **Solution:** Removed `AWS_REGION` from `Globals.Environment.Variables` in the SAM template.
- **Additional Fix:** Rebuilt the SAM artifacts with:
  ```bash
  sam build
  sam deploy
  ```
- **Outcome:** Stack deployed successfully after this change.

#### 5. **Rollback-Complete State Blocks Re-Deploy**
- **Problem:** CloudFormation stack got stuck in `ROLLBACK_COMPLETE`, blocking further deploy attempts.
- **Solution:** Used AWS Console to delete the stack manually before retrying `sam deploy`.
- **Lesson:** In dev mode, avoid enabling rollback unless testing failure paths.

---

### 🏑 Achievements
- ✅ IAM roles modularized
- ✅ Admin/contributor user groups secured
- ✅ First SAM deployment succeeded for all three Lambda functions
- ✅ CloudFormation output confirmed with correct ARNs for each function:
  - `ai-news-scraper`
  - `ai-news-summarizer`
  - `ai-news-poster`

---

### 💡 Lessons for the Future
- Keep IAM policies flexible but explicit. Use least privilege, and always test with real users.
- Rebuild (`sam build`) before every deploy to avoid stale artifacts.
- Validate environment variables against [reserved Lambda keys](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html).
- Manual deletion of stacks may be necessary during development.
- Consider enabling version control of `samconfig.toml` after first successful deploy.

---

### ⚙ Next Tasks
- Hook up CloudWatch log streams for validation
- Begin testing event-driven triggers
- Integrate Secrets Manager and Bedrock invocation permissions into function-level roles

---
**Status:** SAM environment and IAM user scaffolding complete. Ready to build automation layer.

🚀 **v0.4.3** milestone complete.



---

_Last updated: 2025-04-11_
