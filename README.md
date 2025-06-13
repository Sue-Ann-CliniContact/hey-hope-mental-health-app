# 🤖 Hey Trial – Clinical Study Matching Bot for Autism

**Hey Trial** is a conversational assistant that guides users through a consented intake process to match them with actively recruiting **autism-related clinical trials**. It integrates with [ClinicalTrials.gov](https://clinicaltrials.gov), supports structured data capture, and syncs participants to a **Monday.com** lead board.

---

## 🚀 Features

- 🧠 Conversational Q&A flow that mimics human screening
- ✅ Consent-first before collecting data
- 🧾 Collects structured fields (name, age, diagnosis, location, etc.)
- 🧬 Matches trials from a local `indexed_studies.json` (autism only)
- 📍 Filters by age, location (city/state), and optional goals/conditions
- 🔗 Returns trials with eligibility, contact, and link
- 🗂️ Pushes participant data directly to a Monday.com board

---

## 🗂️ Project Structure
├── main.py # Flask API handling chat flow
├── matcher.py # Study filtering and ranking logic
├── helpers.py # Formatter and data extractors
├── push.py # Sends data to Monday.com
├── question_flow.py # One-question-at-a-time logic
├── context_store.py # In-memory session history (temporary)
├── build_study_index.py # Filters + builds autism-only study index
├── startup.py # Downloads & unzips full ClinicalTrials.gov XML
├── data/
│ └── indexed_studies.json # 🔍 Pre-indexed active autism trials

---

## 🛠️ Setup Instructions

### 1. 🔧 Install dependencies

```bash
pip install -r requirements.txt
python startup.py
python main.py
{
  "user_input": "Hi, my child is 8 and has autism",
  "chat_history": []
}

---

Let me know if you'd like:
- A short **demo script** for client testing
- A versioned `CHANGELOG.md`
- Instructions to deploy on Render or Hugging Face Spaces

You’re ready to ship 🚀
