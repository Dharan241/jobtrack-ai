from flask import Flask, render_template, request, jsonify
import sqlite3, os, json, re
from datetime import datetime
from google import genai as google_genai
from dotenv import load_dotenv

load_dotenv()  # loads .env file automatically

app = Flask(__name__)
DB_PATH = "jobtrack.db"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
    print(f"✅ Gemini API key loaded: {GEMINI_API_KEY[:8]}...")
else:
    print("⚠️ No Gemini API key found — using fallback mode")

# ─── DATABASE SETUP ───────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT, role TEXT, status TEXT DEFAULT 'Applied',
        ctc TEXT, location TEXT, applied_date TEXT,
        notes TEXT, link TEXT, source TEXT DEFAULT 'manual',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY,
        name TEXT, email TEXT, cgpa TEXT, batch TEXT, degree TEXT,
        skills TEXT, certifications TEXT, projects TEXT,
        target_roles TEXT, target_ctc TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Insert default profile row
    c.execute('INSERT OR IGNORE INTO profile (id, name) VALUES (1, "")')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def call_gemini(prompt, json_mode=False):
    if not gemini_client:
        return None
    try:
        response = gemini_client.models.generate_content(
            model='gemini-1.5-flash-latest',
            contents=prompt
        )
        text = response.text.strip()
        if json_mode:
            text = re.sub(r'^```json\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            return json.loads(text)
        return text
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

# ─── PROFILE ROUTES ───────────────────────────────────────────────
@app.route('/api/profile', methods=['GET'])
def get_profile():
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
    conn.close()
    if p:
        d = dict(p)
        for f in ['skills','certifications','projects','target_roles']:
            try: d[f] = json.loads(d[f]) if d[f] else []
            except: d[f] = []
        return jsonify(d)
    return jsonify({})

@app.route('/api/profile', methods=['POST'])
def save_profile():
    data = request.json
    conn = get_db()
    conn.execute('''UPDATE profile SET
        name=?, email=?, cgpa=?, batch=?, degree=?,
        skills=?, certifications=?, projects=?, target_roles=?, target_ctc=?,
        updated_at=?
        WHERE id=1''', (
        data.get('name'), data.get('email'), data.get('cgpa'),
        data.get('batch'), data.get('degree'),
        json.dumps(data.get('skills', [])),
        json.dumps(data.get('certifications', [])),
        json.dumps(data.get('projects', [])),
        json.dumps(data.get('target_roles', [])),
        data.get('target_ctc'),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── JOB ROUTES ───────────────────────────────────────────────────
@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    conn = get_db()
    jobs = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(j) for j in jobs])

@app.route('/api/jobs', methods=['POST'])
def add_job():
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO jobs (company, role, status, ctc, location, applied_date, notes, link, source)
        VALUES (?,?,?,?,?,?,?,?,?)''', (
        data.get('company'), data.get('role'), data.get('status','Applied'),
        data.get('ctc'), data.get('location'), data.get('applied_date'),
        data.get('notes'), data.get('link'), data.get('source','manual')
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
def update_job(job_id):
    data = request.json
    conn = get_db()
    conn.execute('UPDATE jobs SET status=?, notes=?, ctc=? WHERE id=?',
        (data.get('status'), data.get('notes'), data.get('ctc'), job_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
    conn = get_db()
    conn.execute('DELETE FROM jobs WHERE id=?', (job_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── EMAIL ANALYZER ───────────────────────────────────────────────
@app.route('/api/analyze-email', methods=['POST'])
def analyze_email():
    data = request.json
    email_text = data.get('email_text', '')

    if not email_text.strip():
        return jsonify({'error': 'No email content provided'}), 400

    # Use Gemini to extract job details
    prompt = f"""You are an expert at reading job application emails and extracting structured data.

Read the email below carefully and extract these details.

IMPORTANT RULES:
- For "company": Look for company name in subject line, sender name, or email body. Examples: "IBM", "TCS", "Infosys", "Deloitte"
- For "role": Look for job title/position. Examples: "Associate Developer", "Software Engineer", "Data Analyst"  
- For "status": 
    * "Applied" = application received/thank you for applying
    * "OA" = online assessment/coding test/HackerRank/Knockri invited
    * "Interview" = interview scheduled/invitation to interview
    * "Offer" = offer letter/selected/congratulations/pleased to offer
    * "Rejected" = regret/not moving forward/unsuccessful
- For "applied_date": Extract any date mentioned, format as YYYY-MM-DD. If not found use today: {datetime.now().strftime('%Y-%m-%d')}
- For "confidence": "high" if company+role clearly found, "medium" if partially found, "low" if guessed

EMAIL CONTENT:
{email_text[:4000]}

Return ONLY this exact JSON with no extra text:
{{
  "company": "extracted company name",
  "role": "extracted job role",
  "status": "Applied or OA or Interview or Offer or Rejected",
  "applied_date": "YYYY-MM-DD",
  "ctc": "salary if mentioned else empty string",
  "location": "location if mentioned else empty string",
  "notes": "one sentence describing what this email is about",
  "confidence": "high or medium or low"
}}"""

    result = call_gemini(prompt, json_mode=True)

    if not result:
        # Fallback: basic keyword extraction
        text_lower = email_text.lower()
        status = 'Applied'
        if any(w in text_lower for w in ['offer letter', 'selected', 'congratulations', 'pleased to offer']):
            status = 'Offer'
        elif any(w in text_lower for w in ['interview', 'schedule a call', 'meet with']):
            status = 'Interview'
        elif any(w in text_lower for w in ['assessment', 'online test', 'coding challenge', 'hackerrank']):
            status = 'OA'
        elif any(w in text_lower for w in ['regret', 'not moving forward', 'not selected', 'unfortunately']):
            status = 'Rejected'

        result = {
            'company': 'Unknown (add manually)',
            'role': 'Unknown (add manually)',
            'status': status,
            'applied_date': '',
            'ctc': '',
            'location': '',
            'notes': 'Extracted via keyword matching. Please review.',
            'confidence': 'low'
        }

    return jsonify(result)

@app.route('/api/analyze-email/save', methods=['POST'])
def save_from_email():
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO jobs (company, role, status, ctc, location, applied_date, notes, source)
        VALUES (?,?,?,?,?,?,?,?)''', (
        data.get('company'), data.get('role'), data.get('status','Applied'),
        data.get('ctc'), data.get('location'), data.get('applied_date'),
        data.get('notes'), 'email'
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── AI JOB FINDER ────────────────────────────────────────────────
@app.route('/api/find-jobs', methods=['POST'])
def find_jobs():
    # Get user profile
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
    conn.close()

    if not p:
        return jsonify({'error': 'Please set up your profile first'}), 400

    profile = dict(p)
    for f in ['skills','certifications','projects','target_roles']:
        try: profile[f] = json.loads(profile[f]) if profile[f] else []
        except: profile[f] = []

    prompt = f"""You are a career advisor helping a fresher find the best job opportunities in India.

CANDIDATE PROFILE:
- Name: {profile.get('name', 'Candidate')}
- Degree: {profile.get('degree', 'B.Tech CSE')}
- Batch: {profile.get('batch', '2026')}
- CGPA: {profile.get('cgpa', 'N/A')}
- Skills: {', '.join(profile.get('skills', []))}
- Certifications: {', '.join(profile.get('certifications', []))}
- Projects: {', '.join(profile.get('projects', []))}
- Target Roles: {', '.join(profile.get('target_roles', []))}
- Target CTC: {profile.get('target_ctc', 'Open')}

Based on this profile, suggest 12 specific job opportunities they should apply to RIGHT NOW in 2026.
Mix of: entry level, mid tier, and a few dream companies.

Return ONLY a JSON array of exactly 12 jobs:
[
  {{
    "company": "Company Name",
    "role": "Exact Role Title",
    "estimated_ctc": "X-Y LPA",
    "match_score": 85,
    "match_reason": "2-sentence reason why this matches their profile",
    "how_to_apply": "Direct URL or platform name",
    "difficulty": "Easy/Medium/Hard",
    "priority": "High/Medium/Low",
    "skills_needed": ["skill1", "skill2"],
    "missing_skills": ["skill they lack but should learn"]
  }}
]

Prioritize roles matching their skills. Be specific with company names (real companies hiring in India 2026).
Return ONLY the JSON array."""

    result = call_gemini(prompt, json_mode=True)

    if not result:
        # Fallback job suggestions
        result = [
            {"company": "IBM", "role": "Associate Developer", "estimated_ctc": "6-8 LPA", "match_score": 90, "match_reason": "Strong CGPA + Python/SQL match IBM's requirements. Already in hiring process.", "how_to_apply": "ibm.com/jobs", "difficulty": "Medium", "priority": "High", "skills_needed": ["Python", "SQL", "OOPs"], "missing_skills": []},
            {"company": "Zoho", "role": "Member Technical Staff", "estimated_ctc": "8-10 LPA", "match_score": 85, "match_reason": "Zoho values strong fundamentals and CGPA. Logic-based test suits your profile.", "how_to_apply": "careers.zoho.com", "difficulty": "Medium", "priority": "High", "skills_needed": ["Java/Python", "Problem Solving"], "missing_skills": ["DSA basics"]},
            {"company": "Capco", "role": "Data Analyst Associate", "estimated_ctc": "6-8 LPA", "match_score": 80, "match_reason": "SQL skills directly match Capco's data analyst requirements.", "how_to_apply": "capco.com/careers", "difficulty": "Easy", "priority": "High", "skills_needed": ["SQL", "Python", "Excel"], "missing_skills": ["Power BI"]},
            {"company": "Accenture", "role": "Associate Software Engineer", "estimated_ctc": "6.5-8 LPA", "match_score": 85, "match_reason": "Mass hiring for 2026 batch. CGPA above cutoff.", "how_to_apply": "accenture.com/careers", "difficulty": "Easy", "priority": "Medium", "skills_needed": ["Any programming language"], "missing_skills": []},
            {"company": "Dell Technologies", "role": "Software Engineer", "estimated_ctc": "8-12 LPA", "match_score": 75, "match_reason": "Good CGPA and Python background. Dell values problem-solving.", "how_to_apply": "dell.com/careers", "difficulty": "Medium", "priority": "High", "skills_needed": ["Python", "SQL", "DSA"], "missing_skills": ["DSA intermediate"]},
        ]

    return jsonify({'jobs': result, 'profile_used': {
        'skills': profile.get('skills', []),
        'certifications': profile.get('certifications', []),
        'target_ctc': profile.get('target_ctc', '')
    }})

# ─── AI PREP ──────────────────────────────────────────────────────
@app.route('/api/ai-prep', methods=['POST'])
def ai_prep():
    data = request.json
    company = data.get('company', '')
    role = data.get('role', '')

    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
    conn.close()

    profile_context = ""
    if p:
        pd = dict(p)
        for f in ['skills','certifications','projects']:
            try: pd[f] = json.loads(pd[f]) if pd[f] else []
            except: pd[f] = []
        profile_context = f"Candidate: {pd.get('degree','B.Tech CSE')}, CGPA {pd.get('cgpa','8.92')}, Skills: {', '.join(pd.get('skills',[]))}, Projects: {', '.join(pd.get('projects',[]))}"

    prompt = f"""You are a career coach for a 2026 B.Tech CSE fresher in India.

{profile_context}

Give a specific, actionable interview preparation guide for:
Company: {company}
Role: {role}

Include:
1. 🔄 Selection process (exact rounds this company typically has)
2. 💻 Technical topics to study (specific to this company)
3. 🧠 Common interview questions (3-4 real questions)
4. 🗣️ HR tips
5. ⚡ 7-day prep timeline
6. 🔗 Best resources

Be specific to {company}. Format with emojis and clear sections."""

    result = call_gemini(prompt)
    if not result:
        result = f"""## {company} — {role} Prep Guide

### 🔄 Typical Selection Process
1. Online Assessment (Aptitude + Coding)
2. Technical Interview (1-2 rounds)
3. HR Interview

### 💻 Key Topics
- Data Structures & Algorithms (Arrays, Strings, HashMap)
- OOPs in Java/Python
- SQL queries (JOINs, GROUP BY, Window functions)
- OS & DBMS fundamentals
- Project explanation

### 🧠 Common Questions
- "Tell me about yourself"
- "Explain your best project end-to-end"
- "Write a program to reverse a string / find duplicates"
- "What is polymorphism? Give a real example"

### ⚡ 7-Day Plan
Day 1-2: Aptitude (IndiaBIX)
Day 3-4: DSA Easy problems (LeetCode)
Day 5: OOPs + SQL revision
Day 6: Mock interview practice
Day 7: Company research + HR prep

### 🔗 Resources
- PrepInsta.com/{company.lower()} (previous papers)
- Glassdoor (interview experiences)
- LeetCode Easy (coding practice)"""

    return jsonify({'prep': result})

# ─── STATS ────────────────────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c']
    by_status = conn.execute('SELECT status, COUNT(*) as c FROM jobs GROUP BY status').fetchall()
    recent = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 3').fetchall()
    conn.close()
    return jsonify({
        'total': total,
        'by_status': [dict(s) for s in by_status],
        'recent': [dict(r) for r in recent]
    })

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    init_db()
    print("\n🚀 JobTrack AI is running at http://localhost:5000\n")
    app.run(debug=True)
