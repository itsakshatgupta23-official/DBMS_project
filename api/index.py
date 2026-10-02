import sys
import os
import traceback

# Ensure root folder is accessible for module imports
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from app import app
except Exception as exc:
    from flask import Flask, jsonify
    err_type = type(exc).__name__
    err_msg = str(exc)
    tb_lines = traceback.format_exc().splitlines()

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def initialization_error(path):
        return jsonify({
            "status": "error",
            "error_type": err_type,
            "message": "Backend initialization failed on Vercel.",
            "detail": err_msg,
            "traceback": tb_lines
        }), 500

# Serverless function entry point
app = app
