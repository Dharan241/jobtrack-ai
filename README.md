# 🚀 JobTrack AI v2.0 — Career Intelligence Platform

A full-stack AI-powered job tracking platform built with Python + Flask + SQLite + Gemini AI.

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Flask](https://img.shields.io/badge/Flask-2.0+-green) ![AI](https://img.shields.io/badge/Gemini-AI-orange) ![SQLite](https://img.shields.io/badge/SQLite-Database-lightgrey)

---

## ✨ Features

### 📋 Application Tracker
- Add, update, delete job applications
- Track status: Applied → OA → Interview → Offer / Rejected
- Filter by status, search by company
- Live stats dashboard

### 📧 Email Analyzer (AI-Powered)
- Paste any job email — AI auto-extracts company, role, status, date
- Detects confirmation emails, OA invites, interview calls, offers, rejections
- One-click save to tracker
- Works with or without Gemini API key

### 🔍 AI Job Finder
- Analyzes your profile (skills, certifications, projects)
- Finds best matching companies and roles
- Shows match %, difficulty, priority, missing skills
- One-click add to tracker + AI prep guide

### 👤 Smart Profile
- Store skills, certifications, projects, target roles
- AI uses this to personalize job matches and prep guides
- Tag-based UI for easy management

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python + Flask |
| Database | SQLite |
| Frontend | HTML + CSS + Vanilla JS |
| AI Engine | Google Gemini 1.5 Flash API |
| Fonts | Outfit + JetBrains Mono |

---

## 🚀 Setup & Run

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/jobtrack-ai.git
cd jobtrack-ai
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Get free Gemini API Key
- Go to: https://aistudio.google.com
- Click "Get API Key" → Create API Key (free)

```bash
# Windows
set GEMINI_API_KEY=your_key_here

# Mac/Linux
export GEMINI_API_KEY=your_key_here
```

> **Note:** App works without API key too — uses smart keyword matching as fallback

### 4. Run the app
```bash
python app.py
```

### 5. Open browser
```
http://localhost:5000
```

---

## 📖 How to Use

### Email Analyzer
1. Open Gmail → Find any job application email
2. Select all (Ctrl+A) → Copy (Ctrl+C)
3. Paste in Email Analyzer tab
4. Click "Analyze Email" → AI extracts all details
5. Review → Save to Applications

### AI Job Finder
1. Fill your profile (Skills, Certs, Projects tab)
2. Go to AI Job Finder tab
3. Click "Find Jobs for Me"
4. AI returns 12 matched companies with % match score
5. Click "+ Track" to add any to your tracker

---

## 🏗️ Project Structure

```
jobtrack-ai/
├── app.py              # Flask backend + REST APIs + AI logic
├── templates/
│   └── index.html      # Full frontend (4 tabs, dark UI)
├── requirements.txt    # Python dependencies
├── jobtrack.db         # SQLite database (auto-created)
└── README.md
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/jobs | Get all jobs |
| POST | /api/jobs | Add a job |
| PUT | /api/jobs/:id | Update job |
| DELETE | /api/jobs/:id | Delete job |
| GET | /api/profile | Get profile |
| POST | /api/profile | Save profile |
| POST | /api/analyze-email | Analyze email with AI |
| POST | /api/analyze-email/save | Save analyzed email |
| POST | /api/find-jobs | AI job finder |
| POST | /api/ai-prep | Get AI prep guide |

---

## 💡 What I Learned Building This

- REST API design with Flask
- SQLite database with multiple tables
- Google Gemini AI API integration
- JSON parsing and error handling
- Full-stack architecture (frontend ↔ backend ↔ database ↔ AI)
- Building something that solves a real personal problem

---

## 🔮 Roadmap

- [ ] Gmail OAuth integration for automatic email sync
- [ ] Resume analyzer + ATS score
- [ ] Analytics charts (application funnel)
- [ ] Email reminders for follow-ups
- [ ] Deploy on Railway/Render

---

## 👨‍💻 Built by

**Gutta Dharan** | B.Tech CSE 2026  
📧 guttadharan241@gmail.com

---

⭐ Star this repo if it helped you!
