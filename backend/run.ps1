# Navigate to backend directory
cd $PSScriptRoot

# Activate virtual environment
.\venv\Scripts\Activate

# Run the dev server. Debug/reloader is controlled by FLASK_DEBUG in .env
# (production defaults to off).
python app.py
