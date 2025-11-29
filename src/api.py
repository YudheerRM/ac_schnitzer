from flask import Flask, send_file, abort
import os

app = Flask(__name__)

# Configuration
# You can change this key to whatever you prefer
SECRET_KEY = "ac_schnitzer_78142" 

# Path to the CSV file
# Assuming this script is in src/, we go up one level to find output/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE_PATH = os.path.join(BASE_DIR, 'output', 'woocommerce_products_updated.csv')

@app.route('/download/<secret_key>')
def download_csv(secret_key):
    """
    Serve the CSV file if the provided secret key matches.
    """
    if secret_key == SECRET_KEY:
        if os.path.exists(CSV_FILE_PATH):
            try:
                return send_file(CSV_FILE_PATH, as_attachment=True, download_name='woocommerce_products_updated.csv')
            except Exception as e:
                return f"Error sending file: {e}", 500
        else:
            return f"File not found at {CSV_FILE_PATH}", 404
    else:
        # Return 403 Forbidden if key doesn't match
        abort(403)

if __name__ == '__main__':
    print(f"Starting API. Download URL: http://localhost:5000/download/{SECRET_KEY}")
    app.run(host='0.0.0.0', port=5000)
