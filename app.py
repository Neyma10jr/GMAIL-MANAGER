import os
import pickle
import base64
import time
import imaplib
from threading import Thread
from flask import Flask, redirect, request, render_template_string, session, url_for
from flask_socketio import SocketIO
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# ---------------- CONFIG ----------------
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

CRED_FILE = r"YOUR_CREDENTIALS_PATH_HERE"
TOKEN_FILE = r"YOUR_TOKEN_PATH_HERE"
EMAILS_DIR = r"YOUR_EMAILS_DIRECTORY_HERE"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
]
REDIRECT_URI = "http://localhost:8000/oauth2callback"

# ---------------- FLASK ----------------
app = Flask(__name__)
app.secret_key = "super_secure_fixed_key_12345"
socketio = SocketIO(app)

# ---------------- GLOBALS ----------------
downloaded_ids = set()
last_10_messages = []
last10_downloaded = False
realtime_started = False

# ---------------- HTML (Complete template) ----------------
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Mailbox+</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.6.1/socket.io.min.js"></script>
<style>
  body { margin:0; padding:0; min-height:100vh; display:flex; flex-direction:column; align-items:center;
         background:#000; color:#fff; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         -webkit-font-smoothing:antialiased; }
  svg { width:120px; height:120px; stroke:url(#gradient); fill:none; stroke-width:2.5; stroke-linecap:round;
        stroke-linejoin:round; stroke-dasharray:300; stroke-dashoffset:300; animation:draw 3s ease-in-out infinite; margin-top:40px;}
  @keyframes draw { 0%{stroke-dashoffset:300;fill:none;} 50%{stroke-dashoffset:0;fill:none;} 70%{stroke-dashoffset:0;fill:url(#gradient);} 100%{stroke-dashoffset:300;fill:none;} }
  h1 { font-size:clamp(40px,6vw,80px); font-weight:700; letter-spacing:-0.02em; text-align:center; margin:20px 0;
       background: linear-gradient(90deg,#ff4b2b,#ff416c,#ffbb00,#3ae374,#1dd1a1,#54a0ff,#5f27cd);
       -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  h2,h3 { text-align:center; margin:10px 0; font-weight:400; color:#fff; }
  .container { width:90%; max-width:900px; text-align:left; margin-bottom:50px; }
  button { padding:12px 25px; margin:10px auto; display:block; border:none; border-radius:8px;
           background:linear-gradient(90deg,#ff416c,#ff4b2b); color:white; cursor:pointer; font-size:18px; transition:0.3s; }
  button:hover { opacity:0.8; }
  input, select { padding:8px 12px; margin:5px 0; border-radius:5px; border:none; width:80%; }
  form { margin:15px 0; display:flex; flex-direction:column; align-items:center; }
  .instructions { background:#111; padding:25px; border-radius:12px; color:#ddd; line-height:1.6; }
  .instructions ul { padding-left:25px; }
  .instructions ul ul { padding-left:25px; }
  a { color:#1dd1a1; text-decoration:none; }
  code { background:#222; padding:2px 5px; border-radius:4px; color:#ffdd00; }
  .storage-bar-container { width:100%; height:20px; background:#222; border-radius:10px; display:flex; overflow:hidden; margin:10px 0; }
  .storage-bar-used { background:linear-gradient(90deg,#ff416c,#ff4b2b,#ffbb00,#3ae374,#1dd1a1,#54a0ff,#5f27cd); transition:width 0.5s; }
  .storage-bar-free { background:#444; transition:width 0.5s; }
  .ticker { overflow:hidden; white-space:nowrap; border-top:1px solid #444; border-bottom:1px solid #444; padding:5px 0; margin-top:15px; width:100%; }
  .ticker span { display:inline-block; padding-left:100%; animation:scroll-left 20s linear infinite; }
  @keyframes scroll-left { 0% { transform:translateX(0%); } 100% { transform:translateX(-100%); } }
</style>
</head>
<body>
<svg viewBox="0 0 24 24">
  <defs>
    <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff4b2b"/>
      <stop offset="25%" stop-color="#ffbb00"/>
      <stop offset="50%" stop-color="#3ae374"/>
      <stop offset="75%" stop-color="#54a0ff"/>
      <stop offset="100%" stop-color="#5f27cd"/>
    </linearGradient>
  </defs>
  <rect x="3" y="5" width="18" height="14" rx="2" ry="2"/>
  <polyline points="3,5 12,13 21,5"/>
</svg>

<h1>Mailbox+</h1>
<div class="container">
{% if not logged_in %}
  <h2>Welcome to Mailbox+</h2>
  <h3>Gmail Manager & Downloader</h3>
  <div class="instructions">
    <h3>Step-by-Step Setup for First-Time Users</h3>
    <ul>
      <li><b>Step 1: Create a Google Cloud Project</b>
        <ul>
          <li>Go to <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Console</a>.</li>
          <li>Click <b>Create Project</b>, give it a name, and click <b>Create</b>.</li>
          <li>Note the <b>Project ID</b> for reference.</li>
        </ul>
      </li>
      <li><b>Step 2: Enable APIs</b>
        <ul>
          <li>Navigate to <b>APIs & Services → Library</b> in your project.</li>
          <li>Enable <b>Gmail API</b> and <b>Google Drive API</b>.</li>
        </ul>
      </li>
      <li><b>Step 3: Create OAuth Credentials</b>
        <ul>
          <li>Go to <b>APIs & Services → Credentials → Create Credentials → OAuth Client ID</b>.</li>
          <li>Select <b>Desktop App</b> as application type.</li>
          <li>Download <b>credentials.json</b> and place it in your project folder.</li>
        </ul>
      </li>
      <li><b>Step 4: Configure Redirect URI</b>
        <ul>
          <li>Set redirect URI to <code>http://localhost:8000/oauth2callback</code>.</li>
        </ul>
      </li>
      <li><b>Step 5: Generate App Password (for deletion)</b>
        <ul>
          <li>Go to <a href="https://myaccount.google.com/apppasswords" target="_blank">App Passwords</a>.</li>
          <li>Select <b>Mail → Other → Enter name → Generate</b>.</li>
        </ul>
      </li>
      <li><b>Step 6: Install Python Dependencies</b>
        <ul>
          <li>Install packages via terminal:</li>
          <li><code>pip install flask flask_socketio google-auth google-auth-oauthlib google-api-python-client</code></li>
        </ul>
      </li>
      <li><b>Step 7: Run the Flask App</b>
        <ul>
          <li>Start Flask server: <code>python app.py</code></li>
          <li>Open <b>http://localhost:8000</b> in your browser.</li>
        </ul>
      </li>
      <li><b>Step 8: Login & Authorize</b>
        <ul>
          <li>Click <b>Login with Google</b> and complete OAuth authorization.</li>
        </ul>
      </li>
      <li><b>Step 9: Use Dashboard</b>
        <ul>
          <li>Download last 10 emails or start real-time download.</li>
          <li>Delete emails from Inbox or All Mail using app password.</li>
          <li>View storage usage with visual bar.</li>
          <li>See recently downloaded emails in scrolling ticker.</li>
        </ul>
      </li>
      <li><b>Step 10: Troubleshooting</b>
        <ul>
          <li>Ensure <b>credentials.json</b> and folder paths are correct.</li>
          <li>Use Chrome/Firefox for OAuth; Edge/IE may fail.</li>
        </ul>
      </li>
    </ul>
  </div>
  <a href="{{ url_for('authorize') }}"><button>Login with Google</button></a>
{% else %}
  <h3>Storage Usage</h3>
  <div class="storage-bar-container">
    <div class="storage-bar-used" id="storageBarUsed"></div>
    <div class="storage-bar-free" id="storageBarFree"></div>
  </div>
  <p>{{ used_gb|round(2) }} GB used of {{ limit_gb|round(2) }} GB</p>

  <h3>Deletion Section</h3>
  {% if used_gb < 14.5 %}
    <form method="post" action="{{ url_for('delete_email') }}">
      <label>Delete which email (Inbox)?</label>
      <select name="deletion_type">
        <option value="oldest">Oldest</option>
        <option value="newest">Newest</option>
      </select><br>
      <input type="email" name="email" placeholder="you@gmail.com" required><br>
      <input type="password" name="app_password" placeholder="16-char app password" required><br>
      <button type="submit">Delete from Inbox</button>
    </form>
  {% else %}
    <form method="post" action="{{ url_for('auto_delete') }}">
      <input type="email" name="email" placeholder="you@gmail.com" required><br>
      <input type="password" name="app_password" placeholder="16-char app password" required><br>
      <button type="submit">Delete Oldest from All Mail</button>
    </form>
  {% endif %}

  <h3>Downloading Section</h3>
  <button onclick="startDownload('last10')">Download Last 10 Emails</button>
  <button onclick="startDownload('realtime')">Start Real-time Download</button>

  <div class="ticker"><span id="emailTicker"></span></div>

  <script>
  var socket = io();
  var ticker = document.getElementById("emailTicker");
  var messages = [];
  function addMessage(msg){ messages.push(msg); ticker.innerHTML = messages.join(" • "); if(messages.length>20) messages.shift(); }
  socket.on('new_email', function(data){ addMessage(data.message); });
  function startDownload(type){ fetch('/start_download?type='+type).then(res=>res.text()).then(msg=>addMessage(msg)); }
  fetch('/initial_messages').then(res=>res.json()).then(data=>{ data.messages.reverse().forEach(msg=>addMessage(msg)); });
  var used = {{ used_gb }}; var limit = {{ limit_gb }};
  var percentage = Math.min((used/limit)*100,100); if(percentage<5) percentage=5;
  document.getElementById("storageBarUsed").style.width = percentage + "%";
  document.getElementById("storageBarFree").style.width = (100-percentage) + "%";
  </script>
{% endif %}
</div>
</body>
</html>
"""

# ---------------- IMAP HELPERS ----------------
def delete_one_from_inbox(user, app_password, which):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, app_password)
    typ, _ = mail.select("INBOX")
    if typ != "OK": mail.logout(); return None
    typ, data = mail.uid("SEARCH", None, "ALL")
    if typ != "OK" or not data or not data[0]: mail.close(); mail.logout(); return None
    uids = data[0].split()
    target_uid = uids[0] if which=="oldest" else uids[-1]
    mail.uid("STORE", target_uid, "+FLAGS", r"(\Deleted)")
    mail.expunge()
    mail.close()
    mail.logout()
    return target_uid.decode()

def delete_oldest_allmail(user, app_password):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, app_password)
    typ, _ = mail.select("[Gmail]/All Mail")
    if typ != "OK": mail.logout(); return None
    typ, data = mail.uid("SEARCH", None, "ALL")
    if typ != "OK" or not data or not data[0]: mail.close(); mail.logout(); return None
    uids = data[0].split()
    target_uid = uids[0]
    mail.uid("STORE", target_uid, "+FLAGS", r"(\Deleted)")
    mail.expunge()
    mail.close()
    mail.logout()
    return target_uid.decode()

# ---------------- EMAIL DOWNLOADER ----------------
def poll_emails(creds):
    global downloaded_ids, last_10_messages
    service = build('gmail','v1',credentials=creds)
    os.makedirs(EMAILS_DIR, exist_ok=True)
    downloaded_ids = set(f.split(".eml")[0] for f in os.listdir(EMAILS_DIR) if f.endswith(".eml"))
    while True:
        try:
            results = service.users().messages().list(userId='me', maxResults=10).execute()
            messages = results.get('messages', [])
            for msg in messages:
                msg_id = msg['id']
                if msg_id in downloaded_ids: continue
                message = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()
                msg_str = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
                with open(os.path.join(EMAILS_DIR,f"{msg_id}.eml"),'wb') as f: f.write(msg_str)
                downloaded_ids.add(msg_id)
                display_msg = f"Downloaded email: {msg_id}"
                last_10_messages.append(display_msg)
                if len(last_10_messages)>10: last_10_messages.pop(0)
                socketio.emit('new_email', {'message': display_msg})
        except: pass
        time.sleep(5)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    logged_in = session.get('logged_in', False)
    used_gb = limit_gb = 0
    if logged_in and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f: creds = pickle.load(f)
        drive_service = build("drive","v3",credentials=creds)
        about = drive_service.about().get(fields="storageQuota").execute()
        used_gb = int(about["storageQuota"]["usage"])/(1024**3)
        limit_gb = int(about["storageQuota"]["limit"])/(1024**3)
    return render_template_string(PAGE_TEMPLATE, logged_in=logged_in, used_gb=used_gb, limit_gb=limit_gb)

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(CRED_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="false")
    session["oauth_state"] = state
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    if "oauth_state" not in session:
        return redirect(url_for("authorize"))
    flow = Flow.from_client_secrets_file(CRED_FILE, scopes=SCOPES, state=session["oauth_state"], redirect_uri=REDIRECT_URI)
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    with open(TOKEN_FILE, "wb") as f: pickle.dump(creds,f)
    session.pop("oauth_state", None)
    session["logged_in"] = True
    return redirect(url_for("index"))

@app.route("/delete_email", methods=["POST"])
def delete_email():
    try:
        uid = delete_one_from_inbox(request.form["email"], request.form["app_password"], request.form["deletion_type"])
        heading = "Success" if uid else "Nothing Deleted"
        message = f"Deleted {request.form['deletion_type']} email (UID {uid})" if uid else "No emails in Inbox"
        return render_template_string("<h2>{{heading}}</h2><p>{{message}}</p><a href='/'>Back</a>", heading=heading, message=message)
    except Exception as e: return str(e)

@app.route("/auto_delete", methods=["POST"])
def auto_delete():
    try:
        uid = delete_oldest_allmail(request.form["email"], request.form["app_password"])
        heading = "Success" if uid else "Nothing Deleted"
        message = f"Deleted oldest All Mail email (UID {uid})" if uid else "No emails in All Mail"
        return render_template_string("<h2>{{heading}}</h2><p>{{message}}</p><a href='/'>Back</a>", heading=heading, message=message)
    except Exception as e: return str(e)

@app.route("/start_download")
def start_download():
    global realtime_started
    type_ = request.args.get("type","last10")
    if not os.path.exists(TOKEN_FILE): return "OAuth token missing."
    with open(TOKEN_FILE,"rb") as f: creds = pickle.load(f)
    if type_=="last10":
        Thread(target=poll_emails,args=(creds,),daemon=True).start()
        return "Last 10 emails downloading..."
    elif type_=="realtime" and not realtime_started:
        Thread(target=poll_emails,args=(creds,),daemon=True).start()
        realtime_started = True
        return "Real-time email downloader started..."
    else: return "Already running."

@app.route("/initial_messages")
def initial_messages():
    return {"messages": last_10_messages}

# ---------------- MAIN ----------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
