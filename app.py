from flask import Flask, redirect, url_for, session, render_template
import os
import warnings
import logging
import json
from config import Config
from auth import auth_bp
from routes.chat_routes import chat_bp

# Suppress warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
app.secret_key = Config.SECRET_KEY

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)

@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    # return redirect(url_for("chat.ai_chat"))
    return render_template("index.html")

@app.template_filter('tojsonfilter')
def to_json_filter(obj):
    if obj is None:
        return 'null'
    return json.dumps(obj, separators=(',', ':'))

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)