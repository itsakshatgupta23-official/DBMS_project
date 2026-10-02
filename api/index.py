import sys
import os

# Ensure root folder is accessible for module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Serverless function entry point
app = app
