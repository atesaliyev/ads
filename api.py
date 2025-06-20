import os
import subprocess
import json
from datetime import datetime
from flask import Flask, request, jsonify, Response
from clicklogs_db import ClickLogsDB

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

@app.route('/logs', methods=['GET'])
def get_logs():
    """
    Get click logs for a specific date or today's logs.
    Query parameters:
    - date: Optional date in DD-MM-YYYY format (default: today)
    - source: Optional source filter ('local', 'supabase', 'both') (default: 'both')
    """
    try:
        # Get date parameter, default to today
        date_param = request.args.get('date')
        if date_param:
            click_date = date_param
        else:
            click_date = datetime.now().strftime("%d-%m-%Y")
        
        # Get source parameter
        source = request.args.get('source', 'both')
        
        # Initialize database
        db = ClickLogsDB()
        
        results = []
        
        # Get local database results
        if source in ['local', 'both']:
            local_results = db.query_clicks(click_date)
            if local_results:
                for result in local_results:
                    results.append({
                        "source": "local",
                        "site_url": result[0],
                        "clicks": result[1],
                        "category": result[2],
                        "click_time": result[3],
                        "query": result[4]
                    })
        
        # Get Supabase results
        if source in ['supabase', 'both'] and hasattr(db, 'supabase_client') and db.supabase_client:
            supabase_results = db.query_clicks_from_supabase(click_date)
            if supabase_results:
                for result in supabase_results:
                    results.append({
                        "source": "supabase",
                        "site_url": result[0],
                        "clicks": result[1],
                        "category": result[2],
                        "click_time": result[3],
                        "query": result[4]
                    })
        
        return jsonify({
            "status": "success",
            "date": click_date,
            "total_records": len(results),
            "data": results
        })
        
    except Exception as e:
        print(f"Error getting logs: {e}")
        return jsonify({"status": "error", "message": f"Failed to get logs: {e}"}), 500

@app.route('/logs/summary', methods=['GET'])
def get_logs_summary():
    """
    Get a summary of click logs for a specific date or today.
    Query parameters:
    - date: Optional date in DD-MM-YYYY format (default: today)
    """
    try:
        # Get date parameter, default to today
        date_param = request.args.get('date')
        if date_param:
            click_date = date_param
        else:
            click_date = datetime.now().strftime("%d-%m-%Y")
        
        # Initialize database
        db = ClickLogsDB()
        
        # Get local database results
        local_results = db.query_clicks(click_date)
        
        summary = {
            "date": click_date,
            "total_clicks": 0,
            "total_sites": 0,
            "categories": {},
            "top_sites": []
        }
        
        if local_results:
            summary["total_sites"] = len(local_results)
            
            for result in local_results:
                site_url, clicks, category, click_time, query = result
                clicks = int(clicks)
                
                summary["total_clicks"] += clicks
                
                # Count by category
                if category not in summary["categories"]:
                    summary["categories"][category] = 0
                summary["categories"][category] += clicks
                
                # Track top sites
                summary["top_sites"].append({
                    "site_url": site_url,
                    "clicks": clicks,
                    "category": category
                })
            
            # Sort top sites by clicks
            summary["top_sites"].sort(key=lambda x: x["clicks"], reverse=True)
            summary["top_sites"] = summary["top_sites"][:10]  # Top 10
        
        return jsonify({
            "status": "success",
            "summary": summary
        })
        
    except Exception as e:
        print(f"Error getting logs summary: {e}")
        return jsonify({"status": "error", "message": f"Failed to get logs summary: {e}"}), 500

@app.route('/docker-logs', methods=['GET'])
def get_docker_logs():
    """
    Get real-time Docker container logs using Server-Sent Events (SSE).
    This allows streaming logs to the client in real-time.
    """
    def generate():
        try:
            # Run docker logs command with follow flag
            process = subprocess.Popen(
                ['docker', 'logs', '-f', 'my-ads-api'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            for line in iter(process.stdout.readline, ''):
                if line:
                    # Send the log line as SSE data
                    yield f"data: {line.strip()}\n\n"
                    
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
        finally:
            if 'process' in locals():
                process.terminate()
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/docker-logs-simple', methods=['GET'])
def get_docker_logs_simple():
    """
    Get recent Docker logs without streaming (for simple viewing).
    Query parameters:
    - lines: Number of lines to fetch (default: 10)
    - tail: Use tail instead of full logs (default: true)
    """
    try:
        lines = request.args.get('lines', '10')
        use_tail = request.args.get('tail', 'true').lower() == 'true'
        
        if use_tail:
            command = ['docker', 'logs', '--tail', lines, 'my-ads-api']
        else:
            command = ['docker', 'logs', 'my-ads-api']
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        if result.returncode == 0:
            return jsonify({
                "status": "success",
                "logs": result.stdout.split('\n') if result.stdout else []
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"Docker command failed: {result.stderr}"
            }), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "message": "Docker logs command timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to get Docker logs: {str(e)}"
        }), 500

if __name__ == '__main__':
    # Listens on all network interfaces, essential for Docker
    app.run(host='0.0.0.0', port=5000) 