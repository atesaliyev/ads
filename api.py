import os
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/run', methods=['POST'])
def run_script():
    """
    Runs the ad_clicker.py script with parameters from the POST request.
    Expects a JSON body with 'query' and optional 'proxy'.
    """
    data = request.get_json()

    if not data or 'query' not in data:
        return jsonify({"status": "error", "message": "Missing 'query' in request body"}), 400

    query = data['query']
    proxy = data.get('proxy') # Proxy is optional

    # --- Construct the command to run the script ---
    # We use 'python' assuming it's in the PATH inside the Docker container.
    command = ["python", "ad_clicker.py", "-q", query]

    if proxy:
        command.extend(["-p", proxy])

    try:
        # --- Run the script in the background ---
        # We use Popen for a non-blocking call. The API will respond immediately.
        # The output (stdout/stderr) is now directed to the container's log.
        subprocess.Popen(command)
        
        print(f"Started ad_clicker.py with query: '{query}'")
        return jsonify({"status": "success", "message": f"Ad clicker process started for query: {query}"})

    except Exception as e:
        print(f"Error starting script: {e}")
        return jsonify({"status": "error", "message": f"Failed to start script: {e}"}), 500

if __name__ == '__main__':
    # Listens on all network interfaces, essential for Docker
    app.run(host='0.0.0.0', port=5000) 