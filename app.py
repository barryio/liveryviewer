from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
from dotenv import load_dotenv
from flask import send_from_directory
import requests
import re



app = Flask(__name__)
app.secret_key = "nothing"  


load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

FLEETS_FILE = "fleets.json"


def load_fleets():
    try:
        with open(FLEETS_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

TABLES_DIR = "data"

def save_fleets(fleets):
    with open(FLEETS_FILE, "w") as file:
        json.dump(fleets, file, indent=4)

def get_table_file(table_name):
    safe_name = re.sub(r'\W+', '', table_name)  # sanitize filename
    return os.path.join(TABLES_DIR, f"table_{safe_name}.json")

def load_table_data(table_name):
    file_path = get_table_file(table_name)
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_table_data(table_name, data):
    os.makedirs(TABLES_DIR, exist_ok=True)
    with open(get_table_file(table_name), "w") as f:
        json.dump(data, f, indent=4)       

@app.route("/api/validate_key", methods=["POST"])
def validate_key():
    data = request.get_json()
    provided_key = data.get("key")
    valid_key = os.getenv("LIST_KEY")

    if provided_key == valid_key:
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False})

# -------------------- Routes --------------------



@app.route('/fleets.json')
def serve_fleets():
    return send_from_directory('.', 'fleets.json') 


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/changes")
def changes():
    return render_template("changes.html")

@app.route("/data-sources")
def data_sources():
    return render_template("data-sources.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")

        if password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", error="Invalid password!")

    return render_template("login.html")


@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("admin.html")


@app.route("/api/fleets", methods=["GET"])
def get_fleets():
    return jsonify(load_fleets())


@app.route("/api/add_fleet", methods=["POST"])
def add_fleet():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid JSON format"}), 400

    fleet = request.get_json()
    
 
    required_fields = ["fleetNumber", "reg", "previousReg", "vehicleType", "livery", "operator"]
    if not all(field in fleet for field in required_fields):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    fleets = load_fleets()
    fleets.append(fleet)
    save_fleets(fleets)
    
    return jsonify({"success": True, "message": "Fleet added successfully"})


@app.route("/api/update_fleet", methods=["POST"])
def update_fleet():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid JSON format"}), 400

    data = request.get_json()
    index = data.get("index")
    updated_fleet = data.get("updatedFleet")

    if index is None or updated_fleet is None:
        return jsonify({"success": False, "error": "Missing index or fleet data"}), 400

    fleets = load_fleets()
    if not (0 <= index < len(fleets)):
        return jsonify({"success": False, "error": "Fleet not found"}), 404

    fleets[index] = updated_fleet
    save_fleets(fleets)
    
    return jsonify({"success": True, "message": "Fleet updated successfully"})


@app.route("/api/delete_fleet", methods=["POST"])
def delete_fleet():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid JSON format"}), 400

    data = request.get_json()
    index = data.get("index")

    if index is None:
        return jsonify({"success": False, "error": "Missing index"}), 400

    fleets = load_fleets()
    if not (0 <= index < len(fleets)):
        return jsonify({"success": False, "error": "Fleet not found"}), 404

    del fleets[index]
    save_fleets(fleets)
    
    return jsonify({"success": True, "message": "Fleet deleted successfully"})

@app.route("/api/request_change", methods=["POST"])
def request_change():
    data = request.get_json()
    
    fleet_number = data.get("fleetNumber")
    reg = data.get("reg")
    new_reg = data.get("newReg", "N/A")
    new_livery = data.get("newLivery", "N/A")
    new_operator = data.get("newOperator", "N/A")
    new_vehicle_type = data.get("newVehicleType", "N/A")
    extra_notes = data.get("extraNotes", "N/A")

    if not fleet_number or not reg:
        return jsonify({"success": False, "message": "Fleet Number and Registration are required!"}), 400


    discord_webhook_url = os.getenv("DISCORD_WEBHOOK")
    if not discord_webhook_url:
        return jsonify({"success": False, "message": "Webhook URL is missing!"}), 500

    message = (
        f"?? **Fleet Change Request** ??\n"
        f"**Fleet Number:** {fleet_number}\n"
        f"**Current Reg:** {reg}\n"
        f"**New Reg:** {new_reg}\n"
        f"**New Livery:** {new_livery}\n"
        f"**New Operator:** {new_operator}\n"
        f"**New Vehicle Type:** {new_vehicle_type}\n"
        f"**Extra Notes:** {extra_notes}"
    )

    # send to discord
    try:
        response = requests.post(discord_webhook_url, json={"content": message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "message": f"Failed to send to Discord: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Change request submitted!"})

@app.route("/api/parse_bulk_fleet", methods=["POST"])
def parse_bulk_fleet():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json()
    text = data.get("bulkText", "")
    livery = data.get("livery", "")
    operator = data.get("operator", "")
    vehicle_type = data.get("vehicleType", None)

    if not livery or not operator:
        return jsonify({"success": False, "error": "Missing livery or operator"}), 400

    lines = text.strip().splitlines()
    parsed_fleets = []

    for line in lines:
        parts = re.split(r'\s+', line.strip())
        if len(parts) < 8:
            continue

        reg = parts[2]
        fleet_number = parts[-1]
        previous_reg = ""

        match = re.search(r"Intended as (\w+)", line)
        if match:
            previous_reg = match.group(1)

        fleet = {
            "fleetNumber": fleet_number,
            "reg": reg,
            "previousReg": previous_reg,
            "vehicleType": vehicle_type if vehicle_type else parts[1],
            "livery": livery,
            "operator": operator,
            "isonbustimes": ""
        }
        parsed_fleets.append(fleet)

    return jsonify({"success": True, "fleets": parsed_fleets})

@app.route("/api/table/<table_name>", methods=["GET"])
def get_table(table_name):
    return jsonify(load_table_data(table_name))

@app.route("/api/table/<table_name>/update", methods=["POST"])
def update_table_row(table_name):
    data = request.get_json()
    index = data.get("index")
    row = data.get("row")

    if index is None or row is None:
        return jsonify({"success": False, "error": "Missing data"}), 400

    table = load_table_data(table_name)
    if not (0 <= index < len(table)):
        return jsonify({"success": False, "error": "Invalid index"}), 400

    table[index] = row
    save_table_data(table_name, table)
    return jsonify({"success": True})

@app.route("/api/table/<table_name>/add", methods=["POST"])
def add_table_row(table_name):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400

    table = load_table_data(table_name)
    table.append(data)
    save_table_data(table_name, table)
    return jsonify({"success": True})

@app.route("/custom-table")
def custom_table():
    return render_template("table.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/fleetshome")
def fleetshome():
    return render_template("lists/flistshome.html")

@app.route("/operators/syrk.html")
def syrklist():
    return render_template("lists/operators/syrk.html")

@app.route("/operators/glcs.html")
def glcslist():
    return render_template("lists/operators/glcs.html")

@app.route("/operators/wray.html")
def wraylist():
    return render_template("lists/operators/wray.html")

@app.route("/lcreator")
def liverycreator():
    return render_template("liverycreator.html")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
