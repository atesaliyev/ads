import os
import subprocess
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# Global variable to hold the running process
process = None
LOG_FILE = "/src/logs/process_log.txt"

def run_script(query):
    """Runs the ad_clicker script in a separate thread"""
    global process
    try:
        # Ensure the log file exists and is empty before starting
        with open(LOG_FILE, "w") as f:
            f.write("Log stream started...\n")
        
        command = ["python", "ad_clicker.py", "--query", query]
        
        # Open the log file in append mode for the subprocess
        with open(LOG_FILE, "a") as log_file:
            process = subprocess.Popen(
                command, 
                stdout=log_file, 
                stderr=subprocess.STDOUT,
                text=True
            )
        process.wait()
    except Exception as e:
        # If something goes wrong, write the error to the log file
        with open(LOG_FILE, "a") as f:
            f.write(f"\n--- SCRIPT FAILED TO START ---\n{str(e)}\n")
    finally:
        process = None

@app.route("/run", methods=["POST"])
def run_ad_clicker():
    global process
    if process and process.poll() is None:
        return jsonify({"status": "error", "message": "A process is already running."}), 409

    query = request.json.get("query")
    if not query:
        return jsonify({"status": "error", "message": "Query parameter is required."}), 400

    # Run the script in a background thread to not block the API
    thread = threading.Thread(target=run_script, args=(query,))
    thread.start()

    return jsonify({"status": "success", "message": f"Ad clicker process started for query: '{query}'. Check /logs for progress."})

@app.route("/logs", methods=["GET"])
def get_logs():
    """Returns the content of the log file."""
    try:
        with open(LOG_FILE, "r") as f:
            logs = f.read()
        # Return logs in a simple text format, preserving line breaks
        return logs, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except FileNotFoundError:
        return "Log file not found. Have you started a process with /run yet?", 404
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

if __name__ == "__main__":
    # Listens on all network interfaces, essential for Docker
    app.run(host="0.0.0.0", port=5000) 