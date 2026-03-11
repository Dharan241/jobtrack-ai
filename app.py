from flask import Flask, render_template, request, jsonify
import sqlite3, os, json, re
from datetime import datetime
from google import genai as google_genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = "jobtrack.db"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
    print(f"✅ Gemini API key loaded: {GEMINI_API_KEY[:8]}...")
else:
    print("⚠️ No Gemini API key found — using fallback mode")


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


# ─── PROFILE ─────────────────────────────────────────────────────

@app.route('/api/profile', methods=['GET'])
def get_profile():
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
    conn.close()
    if p:
        d = dict(p)
        for f in ['skills', 'certifications', 'projects', 'target_roles']:
            try:
                d[f] = json.loads(d[f]) if d[f] else []
            except:
                d[f] = []
        return jsonify(d)
    return jsonify({})


@app.route('/api/profile', methods=['POST'])
def save_profile():
    data = request.json
    conn = get_db()
    conn.execute('''UPDATE profile SET
        name=?, email=?, cgpa=?, batch=?, degree=?,
        skills=?, certifications=?, projects=?, target_roles=?, target_ctc=?,
        updated_at=? WHERE id=1''', (
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


# ─── JOBS ─────────────────────────────────────────────────────────

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
        data.get('company'), data.get('role'), data.get('status', 'Applied'),
        data.get('ctc'), data.get('location'), data.get('applied_date'),
        data.get('notes'), data.get('link'), data.get('source', 'manual')
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


# ─── EMAIL ANALYZER ──────────────────────────────────────────────

@app.route('/api/analyze-email', methods=['POST'])
def analyze_email():
    data = request.json
    email_text = data.get('email_text', '')
    if not email_text.strip():
        return jsonify({'error': 'No email content provided'}), 400

    prompt = f"""You are an expert at reading job application emails and extracting structured data.

Read the email below carefully and extract these details.

IMPORTANT RULES:
- For "company": Look for company name in subject line, sender name, or email body
- For "role": Look for job title/position
- For "status":
    * "Applied" = application received / thank you for applying
    * "OA" = online assessment / coding test / HackerRank / Knockri invited
    * "Interview" = interview scheduled / invitation to interview
    * "Offer" = offer letter / selected / congratulations / pleased to offer
    * "Rejected" = regret / not moving forward / unsuccessful
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
        text_lower = email_text.lower()
        status = 'Applied'
        if any(w in text_lower for w in ['offer letter', 'selected', 'congratulations', 'pleased to offer']):
            status = 'Offer'
        elif any(w in text_lower for w in ['interview', 'schedule a call']):
            status = 'Interview'
        elif any(w in text_lower for w in ['assessment', 'online test', 'hackerrank', 'knockri']):
            status = 'OA'
        elif any(w in text_lower for w in ['regret', 'not moving forward', 'not selected', 'unfortunately']):
            status = 'Rejected'
        result = {'company': 'Unknown', 'role': 'Unknown', 'status': status,
                  'applied_date': '', 'ctc': '', 'location': '',
                  'notes': 'Extracted via keyword matching. Please review.', 'confidence': 'low'}

    return jsonify(result)


@app.route('/api/analyze-email/save', methods=['POST'])
def save_from_email():
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO jobs (company, role, status, ctc, location, applied_date, notes, source)
        VALUES (?,?,?,?,?,?,?,?)''', (
        data.get('company'), data.get('role'), data.get('status', 'Applied'),
        data.get('ctc'), data.get('location'), data.get('applied_date'),
        data.get('notes'), 'email'
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─── AI JOB FINDER ───────────────────────────────────────────────

@app.route('/api/find-jobs', methods=['POST'])
def find_jobs():
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
    conn.close()
    if not p:
        return jsonify({'error': 'Please set up your profile first'}), 400

    profile = dict(p)
    for f in ['skills', 'certifications', 'projects', 'target_roles']:
        try:
            profile[f] = json.loads(profile[f]) if profile[f] else []
        except:
            profile[f] = []

    prompt = f"""You are a career advisor for freshers in India.
CANDIDATE: {profile.get('degree', 'B.Tech CSE')}, Batch {profile.get('batch', '2026')}, CGPA {profile.get('cgpa', 'N/A')}
Skills: {', '.join(profile.get('skills', []))}
Certifications: {', '.join(profile.get('certifications', []))}
Projects: {', '.join(profile.get('projects', []))}
Target CTC: {profile.get('target_ctc', 'Open')}

Suggest 12 specific job opportunities to apply to RIGHT NOW in 2026. Return ONLY a JSON array:
[{{"company":"Name","role":"Exact Role","estimated_ctc":"X-Y LPA","match_score":85,"match_reason":"2 sentences","how_to_apply":"careers.company.com","difficulty":"Easy/Medium/Hard","priority":"High/Medium/Low","skills_needed":["skill1"],"missing_skills":["skill they lack"]}}]
Return ONLY the JSON array."""

    result = call_gemini(prompt, json_mode=True)

    if not result:
        result = [
            {"company": "IBM", "role": "Associate Developer", "estimated_ctc": "6-8 LPA", "match_score": 90,
             "match_reason": "Strong CGPA and Python/SQL match IBM requirements.", "how_to_apply": "ibm.com/jobs",
             "difficulty": "Medium", "priority": "High", "skills_needed": ["Python", "SQL"], "missing_skills": []},
            {"company": "Zoho", "role": "Member Technical Staff", "estimated_ctc": "8-10 LPA", "match_score": 85,
             "match_reason": "Zoho values strong fundamentals.", "how_to_apply": "careers.zoho.com",
             "difficulty": "Medium", "priority": "High", "skills_needed": ["Java", "Problem Solving"], "missing_skills": ["DSA"]},
        ]

    return jsonify({'jobs': result, 'profile_used': {
        'skills': profile.get('skills', []),
        'certifications': profile.get('certifications', []),
        'target_ctc': profile.get('target_ctc', '')
    }})


# ─── AI PREP ─────────────────────────────────────────────────────

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
        for f in ['skills', 'certifications', 'projects']:
            try:
                pd[f] = json.loads(pd[f]) if pd[f] else []
            except:
                pd[f] = []
        profile_context = f"Candidate: {pd.get('degree', 'B.Tech CSE')}, CGPA {pd.get('cgpa', '8.92')}, Skills: {', '.join(pd.get('skills', []))}"

    prompt = f"""You are a career coach for a 2026 B.Tech CSE fresher in India.
{profile_context}
Give a specific preparation guide for: Company: {company}, Role: {role}
Include: 1) Selection process 2) Technical topics 3) Common questions 4) HR tips 5) 7-day prep plan 6) Resources
Be specific to {company}. Use emojis and clear sections."""

    result = call_gemini(prompt)
    if not result:
        result = f"""## {company} — {role} Prep Guide\n\n### 🔄 Selection Process\n1. Online Assessment\n2. Technical Interview\n3. HR Interview\n\n### 💻 Key Topics\n- DSA basics\n- OOPs\n- SQL\n\n### ⚡ 7-Day Plan\nDay 1-2: Aptitude\nDay 3-4: DSA\nDay 5: OOPs + SQL\nDay 6: Mock Interview\nDay 7: Company Research"""

    return jsonify({'prep': result})


# ─── RESUME ANALYZER ─────────────────────────────────────────────

@app.route('/api/analyze-resume', methods=['POST'])
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['resume']
    if not file.filename.endswith('.pdf'):
        return jsonify({'error': 'Please upload a PDF file'}), 400

    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
    except Exception as e:
        return jsonify({'error': 'Could not read PDF'}), 400

    prompt = f"""You are an expert ATS resume reviewer for tech jobs in India.
Analyze this resume for a 2026 B.Tech CSE fresher and return ONLY a JSON object:
{{
  "ats_score": 85,
  "summary": "2 sentence overall assessment",
  "verdict": "Strong or Average or Needs Work",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
  "missing_keywords": ["keyword1", "keyword2", "keyword3"],
  "section_scores": {{
    "education": 90,
    "skills": 80,
    "projects": 85,
    "certifications": 90,
    "experience": 40
  }},
  "improvements": [
    {{"priority": "High", "suggestion": "specific improvement 1"}},
    {{"priority": "High", "suggestion": "specific improvement 2"}},
    {{"priority": "Medium", "suggestion": "specific improvement 3"}}
  ]
}}

RESUME TEXT:
{text[:4000]}

Return ONLY the JSON."""

    result = call_gemini(prompt, json_mode=True)
    if not result:
        return jsonify({'error': 'AI analysis failed. Check your API key.'}), 500

    return jsonify(result)


# ─── ANALYTICS ───────────────────────────────────────────────────

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c']
    by_status = conn.execute('SELECT status, COUNT(*) as c FROM jobs GROUP BY status').fetchall()
    by_date = conn.execute('''
        SELECT applied_date, COUNT(*) as c
        FROM jobs
        WHERE applied_date IS NOT NULL AND applied_date != ""
        GROUP BY applied_date
        ORDER BY applied_date ASC LIMIT 30
    ''').fetchall()
    by_company = conn.execute('''
        SELECT company, status, COUNT(*) as c
        FROM jobs GROUP BY company
        ORDER BY c DESC LIMIT 10
    ''').fetchall()
    responded = conn.execute('SELECT COUNT(*) as c FROM jobs WHERE status != "Applied"').fetchone()['c']
    conn.close()

    response_rate = round((responded / total * 100), 1) if total > 0 else 0
    status_dict = {row['status']: row['c'] for row in by_status}
    offer_rate = round((status_dict.get('Offer', 0) / total * 100), 1) if total > 0 else 0

    return jsonify({
        'total': total,
        'response_rate': response_rate,
        'offer_rate': offer_rate,
        'by_status': [dict(r) for r in by_status],
        'by_date': [dict(r) for r in by_date],
        'by_company': [dict(r) for r in by_company],
        'status_dict': status_dict
    })


# ─── MOCK INTERVIEW ──────────────────────────────────────────────

@app.route('/api/mock-interview', methods=['POST'])
def mock_interview():
    data = request.json
    company = data.get('company', '')
    role = data.get('role', '')
    question = data.get('question', '')
    answer = data.get('answer', '')
    stage = data.get('stage', 'get_question')

    if stage == 'get_question':
        prompt = f"""You are an interviewer at {company} for {role} position.
Generate 1 interview question. Mix technical and behavioral.
Return ONLY JSON:
{{
  "question": "your interview question here",
  "type": "Technical or Behavioral",
  "difficulty": "Easy or Medium or Hard",
  "tip": "one line tip on how to approach this question"
}}"""
        result = call_gemini(prompt, json_mode=True)
        if not result:
            return jsonify({
                "question": f"Tell me about yourself and why you want to join {company}?",
                "type": "Behavioral", "difficulty": "Easy",
                "tip": "Use BAR format — Background, Action, Result"
            })
        return jsonify(result)

    elif stage == 'evaluate':
        prompt = f"""You are an expert interviewer at {company} for {role}.
Question: {question}
Candidate Answer: {answer}

Evaluate and return ONLY JSON:
{{
  "score": 75,
  "verdict": "Good or Excellent or Needs Improvement",
  "feedback": "2-3 sentences of specific feedback",
  "what_was_good": "what they did well",
  "what_to_improve": "specific improvement",
  "ideal_answer_points": ["key point 1", "key point 2", "key point 3"]
}}"""
        result = call_gemini(prompt, json_mode=True)
        if not result:
            return jsonify({
                "score": 70, "verdict": "Good",
                "feedback": "Good attempt. Be more specific with examples.",
                "what_was_good": "Clear communication",
                "what_to_improve": "Add more technical details",
                "ideal_answer_points": ["Be specific", "Use examples", "Keep concise"]
            })
        return jsonify(result)


# ─── MAIN ────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    init_db()
    print("\n🚀 JobTrack AI v3.0 running at http://localhost:5000\n")
    app.run(debug=True)