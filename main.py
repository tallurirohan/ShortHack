from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, send_file
import os
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import openpyxl
import pickle
from io import BytesIO
from chat_model import ExcelChatModel
from llm_chat import ask_mistral
from datetime import timezone
import ollama




app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_key_for_development')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SESSION_TIMEOUT_MINUTES = 10


def create_db():
    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS software_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        software_name TEXT NOT NULL,
        primary_contact TEXT,
        req_number TEXT,
        software_spend REAL,
        contract_file_path TEXT,
        contract_id TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS savings_tracker (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        software_id INTEGER,
        savings_amount REAL,
        saving_description TEXT,
        FOREIGN KEY (software_id) REFERENCES software_data (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS software_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        software_name TEXT NOT NULL,
        assigned_date TEXT NOT NULL,
        sr_number TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS termed_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        termed_date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS procurement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        software_name TEXT,
        vendor TEXT,
        estimated_cost REAL,
        purpose TEXT,
        approval_status TEXT
    )''')
    conn.commit()
    conn.close()


@app.before_request
def before_request():
    if 'user_id' in session:
        last_active = session.get('_session_last_active', None)
        if last_active:
            last_active = last_active.replace(tzinfo=None)
            if datetime.utcnow() - last_active > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                session.clear()
                flash('Session timed out.', 'warning')
                return redirect(url_for('login'))
        session['_session_last_active'] = datetime.utcnow()


@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    session.pop('_session_last_active', None)
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect('SAMdashboard.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    session.pop('_session_last_active', None)
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed = generate_password_hash(password)
        try:
            conn = sqlite3.connect('SAMdashboard.db')
            conn.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, hashed))
            conn.commit()
            conn.close()
            flash('Registered successfully!', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    c.execute('SELECT * FROM software_data')
    software_entries = c.fetchall()
    conn.close()
    return render_template('dashboard.html', software_entries=software_entries)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/submit', methods=['POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    software_name = request.form['software_name']
    primary_contact = request.form['primary_contact']
    req_number = request.form['req_number']
    software_spend = request.form['software_spend']
    contract_id = request.form['contract_id']
    file = request.files['contract_file']
    file_path = None

    if file:
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        file_path = path

    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    c.execute('''INSERT INTO software_data (software_name, primary_contact, req_number, software_spend, contract_file_path, contract_id)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (software_name, primary_contact, req_number, software_spend, file_path, contract_id))
    conn.commit()
    conn.close()
    flash('Entry added!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    c.execute('SELECT * FROM software_data WHERE id = ?', (id,))
    entry = c.fetchone()
    if request.method == 'POST':
        name = request.form['software_name']
        contact = request.form['primary_contact']
        req = request.form['req_number']
        spend = request.form['software_spend']
        contract_id = request.form['contract_id']
        file = request.files['contract_file']
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            c.execute('''UPDATE software_data SET software_name=?, primary_contact=?, req_number=?, software_spend=?, contract_file_path=?, contract_id=? WHERE id=?''',
                      (name, contact, req, spend, file_path, contract_id, id))
        else:
            c.execute('''UPDATE software_data SET software_name=?, primary_contact=?, req_number=?, software_spend=?, contract_id=? WHERE id=?''',
                      (name, contact, req, spend, contract_id, id))
        conn.commit()
        conn.close()
        flash('Updated successfully.', 'success')
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('edit.html', software_entry=entry)


def calculate_compliance(spend):
    return 80 if spend > 50000 else 50


@app.route('/reports')
def reports_dashboard():
    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    c.execute('SELECT * FROM software_data')
    entries = c.fetchall()
    conn.close()

    total_spend = sum(float(e[4]) for e in entries)
    average_compliance = sum(calculate_compliance(float(e[4])) for e in entries) / len(entries) if entries else 0

    formatted = [{
        'id': e[0],
        'software_name': e[1],
        'primary_contact': e[2],
        'req_number': e[3],
        'software_spend': e[4],
        'compliance': calculate_compliance(float(e[4]))
    } for e in entries]

    return render_template('reports_dashboard.html', software_entries=formatted,
                           total_spend=total_spend,
                           average_compliance="{:.2f}".format(average_compliance))


@app.route('/savings_tracker', methods=['GET', 'POST'])
def savings_tracker():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('SAMdashboard.db')
    c = conn.cursor()
    if request.method == 'POST':
        c.execute('INSERT INTO savings_tracker (software_id, savings_amount, saving_description) VALUES (?, ?, ?)',
                  (request.form['software_id'], request.form['savings_amount'], request.form['saving_description']))
        conn.commit()
        flash('Savings recorded.', 'success')

    c.execute('''SELECT st.id, st.software_id, st.savings_amount, st.saving_description, sd.software_name
                 FROM savings_tracker st INNER JOIN software_data sd ON st.software_id = sd.id''')
    savings_entries = c.fetchall()
    c.execute('SELECT id, software_name FROM software_data')
    options = c.fetchall()
    conn.close()
    return render_template('savings_tracker.html', savings_entries=savings_entries, software_options=options)


@app.route('/catalog', methods=['GET', 'POST'])
def catalog():
    conn = sqlite3.connect('SAMdashboard.db')
    conn.row_factory = sqlite3.Row
    if request.method == 'POST':
        search = request.form.get('search_query', '')
        rows = conn.execute("SELECT * FROM software_catalog WHERE user_name LIKE ? OR software_name LIKE ? OR sr_number LIKE ?",
                            ('%' + search + '%',) * 3).fetchall()
    else:
        rows = conn.execute("SELECT * FROM software_catalog").fetchall()
    conn.close()
    return render_template('catalog.html', catalog_entries=rows)


@app.route('/add_entry', methods=['POST'])
def add_entry():
    conn = sqlite3.connect('SAMdashboard.db')
    conn.execute('INSERT INTO software_catalog (user_name, software_name, assigned_date, sr_number) VALUES (?, ?, ?, ?)',
                 (request.form['user_name'], request.form['software_name'], request.form['assigned_date'], request.form['sr_number']))
    conn.commit()
    conn.close()
    return redirect(url_for('catalog'))


@app.route('/procurement', methods=['GET', 'POST'])
def procurement():
    conn = sqlite3.connect('SAMdashboard.db')
    if request.method == 'POST':
        conn.execute('INSERT INTO procurement (software_name, vendor, estimated_cost, purpose, approval_status) VALUES (?, ?, ?, ?, ?)',
                     (request.form['softwareName'], request.form['vendor'], request.form['estimatedCost'], request.form['purpose'], 'Pending'))
        conn.commit()
        return redirect(url_for('procurement'))
    rows = conn.execute('SELECT * FROM procurement ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('procurement.html', entries=rows)


@app.route('/process_approval/<int:id>/<action>')
def process_approval(id, action):
    status = 'Approved' if action == 'approve' else 'Rejected'
    conn = sqlite3.connect('SAMdashboard.db')
    conn.execute('UPDATE procurement SET approval_status = ? WHERE id = ?', (status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('procurement'))


@app.route('/generate_report', methods=['GET', 'POST'])
def generate_report():
    if request.method == 'POST':
        file = request.files['excel_file']
        path = 'temp.xlsx'
        file.save(path)
        df = pd.read_excel(path)
        if 'username' not in df.columns:
            flash("Username column missing.", "danger")
            return redirect(url_for('generate_report'))

        usernames = df['username'].tolist()
        conn = sqlite3.connect('SAMdashboard.db')
        catalog = conn.execute('SELECT * FROM software_catalog').fetchall()
        conn.close()

        filtered = [r for r in catalog if r[1] in usernames]
        report_df = pd.DataFrame(filtered, columns=['ID', 'user_name', 'software_name', 'assigned_date', 'sr_number'])
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        report_df.to_excel(writer, index=False, sheet_name='Report')
        writer.save()
        output.seek(0)
        os.remove(path)
        return send_file(output, download_name="report.xlsx", as_attachment=True)

    return render_template('generate_report.html')


# Load trained model and dataframe
MODEL_PATH = 'trained_model.pkl'
EXCEL_PATH = 'ai_tools.xlsx'

try:
    with open(MODEL_PATH, 'rb') as f:
        chat_model = pickle.load(f)
    chat_df = pd.read_excel(EXCEL_PATH)
except Exception as e:
    print(f"❌ Failed to load model or Excel: {e}")
    chat_model = None
@app.route('/ai_dashboard', methods=['GET', 'POST'])
def ai_dashboard():
    if 'chat_history' not in session:
        session['chat_history'] = []

    chat_history = session['chat_history']

    if request.method == 'POST':
        prompt = request.form.get('prompt', '').strip()
        if prompt:
            chat_history.append({'role': 'user', 'message': prompt})
            try:
                response = ollama.chat(model='mistral', messages=[
                    {'role': 'system', 'content': (
                        'You are a concise, intelligent assistant for software-related questions. '
                        'Avoid repeating earlier answers. Focus only on the current user query. '
                        'If the topic is already discussed, refer to previous responses briefly without re-explaining everything.'
                    )},

                    *[{ 'role': m['role'], 'content': m['message'] } for m in chat_history[-5:]]

                ])
                ai_reply = response['message']['content']
            except Exception as e:
                ai_reply = f"⚠️ Failed to generate response: {str(e)}"

            chat_history.append({'role': 'ai', 'message': ai_reply})
            session['chat_history'] = chat_history

    return render_template('ai_dashboard.html', chat_history=chat_history)



@app.route('/reset_chat')
def reset_chat():
    session.pop('chat_history', None)
    return redirect(url_for('ai_dashboard'))


# Initialize DB
create_db()

if __name__ == '__main__':
    app.run(debug=True)
