from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3, os, json, re
from datetime import datetime
from google import genai as google_genai
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
import functools

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '0'
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jobtrack-ai-secret-2026")
DB_PATH = "jobtrack.db"

# ─── GEMINI ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
    print(f"✅ Gemini API key loaded: {GEMINI_API_KEY[:8]}...")
else:
    print("⚠️ No Gemini API key found")

# ─── GOOGLE OAUTH ────────────────────────────────────────────────
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ─── DATABASE ────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        google_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        avatar TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        company TEXT, role TEXT, status TEXT DEFAULT 'Applied',
        ctc TEXT, location TEXT, applied_date TEXT,
        notes TEXT, link TEXT, source TEXT DEFAULT 'manual',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        name TEXT, email TEXT, cgpa TEXT, batch TEXT, degree TEXT,
        skills TEXT, certifications TEXT, projects TEXT,
        target_roles TEXT, target_ctc TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
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

# ─── AUTH DECORATOR ──────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    return session.get('user_id')

# ─── AUTH ROUTES ─────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('index.html',
                           user_name=session.get('user_name', ''),
                           user_avatar=session.get('user_avatar', ''))

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect('/')
    error = request.args.get('error')
    return render_template('auth.html', error=error)

@app.route('/auth/google')
def auth_google():
    redirect_uri = "https://jobtrack-ai-production.up.railway.app/auth/callback"
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            return redirect('/login?error=failed')

        google_id = user_info['sub']
        name = user_info['name']
        email = user_info['email']
        avatar = user_info.get('picture', '')

        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE google_id=?', (google_id,)).fetchone()
        if user:
            conn.execute('UPDATE users SET name=?,email=?,avatar=? WHERE google_id=?',
                        (name, email, avatar, google_id))
        else:
            conn.execute('INSERT INTO users (google_id,name,email,avatar) VALUES (?,?,?,?)',
                        (google_id, name, email, avatar))
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE google_id=?', (google_id,)).fetchone()
            conn.execute('INSERT OR IGNORE INTO profile (user_id,name,email) VALUES (?,?,?)',
                        (user['id'], name, email))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE google_id=?', (google_id,)).fetchone()
        conn.close()

        session['user_id'] = user['id']
        session['user_name'] = name
        session['user_email'] = email
        session['user_avatar'] = avatar
        return redirect('/')
    except Exception as e:
        print(f"Auth error: {e}")
        return redirect('/login?error=failed')

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/me', methods=['GET'])
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False}), 401
    return jsonify({
        'logged_in': True,
        'name': session.get('user_name'),
        'email': session.get('user_email'),
        'avatar': session.get('user_avatar')
    })

# ─── PROFILE ─────────────────────────────────────────────────────
@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    user_id = get_current_user()
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE user_id=?', (user_id,)).fetchone()
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
@login_required
def save_profile():
    user_id = get_current_user()
    data = request.json
    conn = get_db()
    existing = conn.execute('SELECT id FROM profile WHERE user_id=?', (user_id,)).fetchone()
    if existing:
        conn.execute('''UPDATE profile SET name=?,email=?,cgpa=?,batch=?,degree=?,
            skills=?,certifications=?,projects=?,target_roles=?,target_ctc=?,updated_at=?
            WHERE user_id=?''', (
            data.get('name'), data.get('email'), data.get('cgpa'),
            data.get('batch'), data.get('degree'),
            json.dumps(data.get('skills', [])),
            json.dumps(data.get('certifications', [])),
            json.dumps(data.get('projects', [])),
            json.dumps(data.get('target_roles', [])),
            data.get('target_ctc'), datetime.now().isoformat(), user_id
        ))
    else:
        conn.execute('''INSERT INTO profile
            (user_id,name,email,cgpa,batch,degree,skills,certifications,projects,target_roles,target_ctc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
            user_id, data.get('name'), data.get('email'), data.get('cgpa'),
            data.get('batch'), data.get('degree'),
            json.dumps(data.get('skills', [])),
            json.dumps(data.get('certifications', [])),
            json.dumps(data.get('projects', [])),
            json.dumps(data.get('target_roles', [])),
            data.get('target_ctc')
        ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── JOBS ─────────────────────────────────────────────────────────
@app.route('/api/jobs', methods=['GET'])
@login_required
def get_jobs():
    user_id = get_current_user()
    conn = get_db()
    jobs = conn.execute(
        'SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC', (user_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(j) for j in jobs])

@app.route('/api/jobs', methods=['POST'])
@login_required
def add_job():
    user_id = get_current_user()
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO jobs
        (user_id,company,role,status,ctc,location,applied_date,notes,link,source)
        VALUES (?,?,?,?,?,?,?,?,?,?)''', (
        user_id, data.get('company'), data.get('role'),
        data.get('status', 'Applied'), data.get('ctc'),
        data.get('location'), data.get('applied_date'),
        data.get('notes'), data.get('link'), data.get('source', 'manual')
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
@login_required
def update_job(job_id):
    user_id = get_current_user()
    data = request.json
    conn = get_db()
    conn.execute(
        'UPDATE jobs SET status=?,notes=?,ctc=? WHERE id=? AND user_id=?',
        (data.get('status'), data.get('notes'), data.get('ctc'), job_id, user_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    user_id = get_current_user()
    conn = get_db()
    conn.execute('DELETE FROM jobs WHERE id=? AND user_id=?', (job_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── EMAIL ANALYZER ──────────────────────────────────────────────
@app.route('/api/analyze-email', methods=['POST'])
@login_required
def analyze_email():
    data = request.json
    email_text = data.get('email_text', '')
    if not email_text.strip():
        return jsonify({'error': 'No email content provided'}), 400

    prompt = (
        "You are an expert at reading job application emails.\n"
        "Read this email and extract job application information.\n"
        "Return ONLY this JSON:\n"
        "{\n"
        '  "company": "company name",\n'
        '  "role": "job role",\n'
        '  "status": "Applied or OA or Interview or Offer or Rejected",\n'
        '  "applied_date": "YYYY-MM-DD or empty",\n'
        '  "ctc": "salary if mentioned or empty",\n'
        '  "location": "location if mentioned or empty",\n'
        '  "notes": "one sentence summary",\n'
        '  "confidence": "high or medium or low"\n'
        "}\n"
        "Status rules: confirmation=Applied, assessment/test/knockri=OA, "
        "interview=Interview, offer/selected=Offer, rejected=Rejected\n"
        f"Today: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"EMAIL: {email_text[:4000]}\n"
        "Return ONLY the JSON."
    )

    result = call_gemini(prompt, json_mode=True)
    if not result:
        text_lower = email_text.lower()
        status = 'Applied'
        if any(w in text_lower for w in ['offer letter', 'selected', 'congratulations']):
            status = 'Offer'
        elif any(w in text_lower for w in ['interview', 'schedule']):
            status = 'Interview'
        elif any(w in text_lower for w in ['assessment', 'test', 'hackerrank', 'knockri']):
            status = 'OA'
        elif any(w in text_lower for w in ['regret', 'not selected', 'unfortunately']):
            status = 'Rejected'
        result = {
            'company': 'Unknown', 'role': 'Unknown', 'status': status,
            'applied_date': '', 'ctc': '', 'location': '',
            'notes': 'Extracted via keyword matching.', 'confidence': 'low'
        }
    return jsonify(result)

@app.route('/api/analyze-email/save', methods=['POST'])
@login_required
def save_from_email():
    user_id = get_current_user()
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO jobs
        (user_id,company,role,status,ctc,location,applied_date,notes,source)
        VALUES (?,?,?,?,?,?,?,?,?)''', (
        user_id, data.get('company'), data.get('role'),
        data.get('status', 'Applied'), data.get('ctc'),
        data.get('location'), data.get('applied_date'),
        data.get('notes'), 'email'
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── AI JOB FINDER ───────────────────────────────────────────────
@app.route('/api/find-jobs', methods=['POST'])
@login_required
def find_jobs():
    user_id = get_current_user()
    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    if not p:
        return jsonify({'error': 'Please set up your profile first'}), 400

    profile = dict(p)
    for f in ['skills', 'certifications', 'projects', 'target_roles']:
        try:
            profile[f] = json.loads(profile[f]) if profile[f] else []
        except:
            profile[f] = []

    prompt = (
        "You are a career advisor for freshers in India.\n"
        f"CANDIDATE: {profile.get('degree', 'B.Tech CSE')}, "
        f"Batch {profile.get('batch', '2026')}, CGPA {profile.get('cgpa', 'N/A')}\n"
        f"Skills: {', '.join(profile.get('skills', []))}\n"
        f"Certifications: {', '.join(profile.get('certifications', []))}\n"
        f"Projects: {', '.join(profile.get('projects', []))}\n"
        f"Target CTC: {profile.get('target_ctc', 'Open')}\n"
        "Suggest 12 specific job opportunities for 2026. Return ONLY a JSON array:\n"
        '[{"company":"Name","role":"Role","estimated_ctc":"X-Y LPA",'
        '"match_score":85,"match_reason":"2 sentences","how_to_apply":"careers.company.com",'
        '"difficulty":"Easy/Medium/Hard","priority":"High/Medium/Low",'
        '"skills_needed":["skill"],"missing_skills":["skill"]}]'
    )

    result = call_gemini(prompt, json_mode=True)
    if not result:
        result = [{
            "company": "IBM", "role": "Associate Developer",
            "estimated_ctc": "6-8 LPA", "match_score": 90,
            "match_reason": "Strong profile match.",
            "how_to_apply": "ibm.com/jobs",
            "difficulty": "Medium", "priority": "High",
            "skills_needed": ["Python", "SQL"], "missing_skills": []
        }]
    return jsonify({
        'jobs': result,
        'profile_used': {
            'skills': profile.get('skills', []),
            'certifications': profile.get('certifications', []),
            'target_ctc': profile.get('target_ctc', '')
        }
    })

# ─── AI PREP + COVER LETTER ──────────────────────────────────────
@app.route('/api/ai-prep', methods=['POST'])
@login_required
def ai_prep():
    user_id = get_current_user()
    data = request.json
    company = data.get('company', '')
    role = data.get('role', '')
    is_cover = data.get('cover_letter', False)

    conn = get_db()
    p = conn.execute('SELECT * FROM profile WHERE user_id=?', (user_id,)).fetchone()
    conn.close()

    profile_context = ""
    if p:
        pd = dict(p)
        for f in ['skills', 'certifications', 'projects']:
            try:
                pd[f] = json.loads(pd[f]) if pd[f] else []
            except:
                pd[f] = []
        profile_context = (
            f"Name: {pd.get('name', '')}, "
            f"Degree: {pd.get('degree', 'B.Tech CSE')}, "
            f"CGPA: {pd.get('cgpa', '')}, "
            f"Skills: {', '.join(pd.get('skills', []))}, "
            f"Certs: {', '.join(pd.get('certifications', []))}, "
            f"Projects: {', '.join(pd.get('projects', []))}"
        )

    if is_cover:
        tone = data.get('tone', 'professional')
        jd = data.get('jd', '')
        name = data.get('name', session.get('user_name', 'Candidate'))
        jd_line = f"Job requirements: {jd}" if jd else ""
        prompt = (
            f"Write a {tone} cover letter for a 2026 B.Tech CSE fresher.\n"
            f"Candidate: {profile_context}\n"
            f"Applying to: {company} for {role}\n"
            f"{jd_line}\n"
            "- 3-4 paragraphs, under 350 words\n"
            '- Start with "Dear Hiring Manager,"\n'
            "- Mention specific matching skills and one project\n"
            "- End with enthusiasm and call to action\n"
            f"- Sign off as {name}\n"
            f"- Tone: {tone}\n"
            "Write the complete cover letter:"
        )
        result = call_gemini(prompt)
        if not result:
            result = (
                "Dear Hiring Manager,\n\n"
                f"I am writing to express my strong interest in the {role} position at {company}. "
                "As a final year B.Tech Computer Science student with a strong academic record, "
                "I am excited about the opportunity to contribute to your team.\n\n"
                "Throughout my academic journey, I have developed strong technical skills and built "
                "real-world projects. My project JobTrack AI — a full-stack AI-powered career platform — "
                "showcases my ability to work with Python, Flask, SQLite, and Gemini AI.\n\n"
                f"I would welcome the opportunity to discuss how I can contribute to {company}. "
                "Thank you for considering my application.\n\n"
                f"Sincerely,\n{name}"
            )
        return jsonify({'cover_letter': result})

    prompt = (
        "You are a career coach for a 2026 B.Tech CSE fresher in India.\n"
        f"{profile_context}\n"
        f"Give a specific prep guide for: {company} — {role}\n"
        "Include: 1) Selection process 2) Technical topics 3) Common questions "
        "4) HR tips 5) 7-day plan 6) Resources\n"
        "Use emojis and clear sections."
    )
    result = call_gemini(prompt)
    if not result:
        result = (
            f"## {company} — {role} Prep Guide\n\n"
            "### 🔄 Process\n1. OA\n2. Technical Interview\n3. HR\n\n"
            "### 💻 Topics\n- DSA, OOPs, SQL\n\n"
            "### ⚡ 7-Day Plan\nDay 1-2: Aptitude\nDay 3-4: DSA\n"
            "Day 5: OOPs+SQL\nDay 6: Mock Interview\nDay 7: Research"
        )
    return jsonify({'prep': result})

# ─── RESUME ANALYZER ─────────────────────────────────────────────
@app.route('/api/analyze-resume', methods=['POST'])
@login_required
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
    except Exception:
        return jsonify({'error': 'Could not read PDF'}), 400

    prompt = (
        "You are an ATS resume reviewer for tech jobs in India.\n"
        "Analyze this 2026 B.Tech CSE fresher resume. Return ONLY JSON:\n"
        "{\n"
        '  "ats_score": 85,\n'
        '  "summary": "2 sentence assessment",\n'
        '  "verdict": "Strong or Average or Needs Work",\n'
        '  "strengths": ["s1","s2","s3"],\n'
        '  "weaknesses": ["w1","w2","w3"],\n'
        '  "missing_keywords": ["k1","k2","k3"],\n'
        '  "section_scores": {"education":90,"skills":80,"projects":85,"certifications":90,"experience":40},\n'
        '  "improvements": [{"priority":"High","suggestion":"s1"},{"priority":"Medium","suggestion":"s2"}]\n'
        "}\n"
        f"RESUME: {text[:4000]}\n"
        "Return ONLY the JSON."
    )

    result = call_gemini(prompt, json_mode=True)
    if not result:
        return jsonify({'error': 'AI analysis failed. Check API key.'}), 500
    return jsonify(result)

# ─── ANALYTICS ───────────────────────────────────────────────────
@app.route('/api/analytics', methods=['GET'])
@login_required
def get_analytics():
    user_id = get_current_user()
    conn = get_db()
    total = conn.execute(
        'SELECT COUNT(*) as c FROM jobs WHERE user_id=?', (user_id,)
    ).fetchone()['c']
    by_status = conn.execute(
        'SELECT status, COUNT(*) as c FROM jobs WHERE user_id=? GROUP BY status', (user_id,)
    ).fetchall()
    by_date = conn.execute(
        '''SELECT applied_date, COUNT(*) as c FROM jobs
        WHERE user_id=? AND applied_date IS NOT NULL AND applied_date != ""
        GROUP BY applied_date ORDER BY applied_date ASC LIMIT 30''', (user_id,)
    ).fetchall()
    by_company = conn.execute(
        '''SELECT company, COUNT(*) as c FROM jobs
        WHERE user_id=? GROUP BY company ORDER BY c DESC LIMIT 10''', (user_id,)
    ).fetchall()
    responded = conn.execute(
        'SELECT COUNT(*) as c FROM jobs WHERE user_id=? AND status != "Applied"', (user_id,)
    ).fetchone()['c']
    conn.close()

    response_rate = round((responded / total * 100), 1) if total > 0 else 0
    status_dict = {row['status']: row['c'] for row in by_status}
    offer_rate = round((status_dict.get('Offer', 0) / total * 100), 1) if total > 0 else 0

    return jsonify({
        'total': total, 'response_rate': response_rate, 'offer_rate': offer_rate,
        'by_status': [dict(r) for r in by_status],
        'by_date': [dict(r) for r in by_date],
        'by_company': [dict(r) for r in by_company],
        'status_dict': status_dict
    })

# ─── MOCK INTERVIEW ──────────────────────────────────────────────
@app.route('/api/mock-interview', methods=['POST'])
@login_required
def mock_interview():
    data = request.json
    company = data.get('company', '')
    role = data.get('role', '')
    question = data.get('question', '')
    answer = data.get('answer', '')
    stage = data.get('stage', 'get_question')

    if stage == 'get_question':
        prompt = (
            f"You are an interviewer at {company} for {role}.\n"
            "Generate 1 interview question. Mix technical and behavioral.\n"
            "Return ONLY JSON:\n"
            '{"question":"question here","type":"Technical or Behavioral",'
            '"difficulty":"Easy or Medium or Hard","tip":"one line tip"}'
        )
        result = call_gemini(prompt, json_mode=True)
        if not result:
            return jsonify({
                "question": f"Tell me about yourself and why {company}?",
                "type": "Behavioral", "difficulty": "Easy", "tip": "Use STAR format"
            })
        return jsonify(result)

    elif stage == 'evaluate':
        prompt = (
            "Evaluate this interview answer.\n"
            f"Company: {company}, Role: {role}\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            "Return ONLY JSON:\n"
            '{"score":75,"verdict":"Good or Excellent or Needs Improvement",'
            '"feedback":"2-3 sentences","what_was_good":"strength",'
            '"what_to_improve":"improvement","ideal_answer_points":["p1","p2","p3"]}'
        )
        result = call_gemini(prompt, json_mode=True)
        if not result:
            return jsonify({
                "score": 70, "verdict": "Good", "feedback": "Good attempt.",
                "what_was_good": "Clear communication",
                "what_to_improve": "Add more details",
                "ideal_answer_points": ["Be specific", "Use examples"]
            })
        return jsonify(result)

# ─── MAIN ────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print("\n🚀 JobTrack AI v5.0 running at http://localhost:5000\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)