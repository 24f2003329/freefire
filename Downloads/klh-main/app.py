import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from utils.gemini_analyzer import analyze_car_damage
# from utils.policy_rag import ingest_policy, query_policy, list_policies, delete_policy
from dotenv import load_dotenv
from utils.negotiation_agent import run_negotiation, get_providers
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = os.path.join("static", "uploads")
POLICY_FOLDER = os.path.join("static", "policies")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["POLICY_FOLDER"] = POLICY_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(POLICY_FOLDER, exist_ok=True)

ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}
ALLOWED_PDF = {"pdf"}


def allowed_image(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_IMAGES


def allowed_pdf(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_PDF


# ============ HOME ============
@app.route("/")
def home():
    return render_template("home.html")


# ============ CLAIM ESTIMATOR ============
@app.route("/claim")
def claim():
    return render_template("claim.html")


@app.route("/claim/analyze", methods=["POST"])
def analyze():
    if "car_image" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("claim"))

    file = request.files["car_image"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("claim"))

    if not allowed_image(file.filename):
        flash("Invalid file type. Upload PNG, JPG, JPEG, or WEBP.", "error")
        return redirect(url_for("claim"))

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        result = analyze_car_damage(filepath)
        image_url = url_for("static", filename=f"uploads/{filename}")
        return render_template("result.html", result=result, image_url=image_url)
    except Exception as e:
        flash(f"Analysis failed: {str(e)}", "error")
        return redirect(url_for("claim"))


# # ============ POLICY Q&A ============
# @app.route("/policy")
# def policy():
#     policies = list_policies()
#     return render_template("policy.html", policies=policies)


# @app.route("/policy/upload", methods=["POST"])
# def upload_policy():
#     if "policy_pdf" not in request.files:
#         flash("No file selected.", "error")
#         return redirect(url_for("policy"))

#     file = request.files["policy_pdf"]
#     policy_name = request.form.get("policy_name", "").strip()

#     if file.filename == "":
#         flash("No file selected.", "error")
#         return redirect(url_for("policy"))

#     if not policy_name:
#         policy_name = file.filename.rsplit(".", 1)[0]

#     if not allowed_pdf(file.filename):
#         flash("Please upload a PDF file.", "error")
#         return redirect(url_for("policy"))

#     filename = secure_filename(f"{uuid.uuid4().hex}.pdf")
#     filepath = os.path.join(app.config["POLICY_FOLDER"], filename)
#     file.save(filepath)

#     try:
#         result = ingest_policy(filepath, policy_name)
#         if result["status"] == "success":
#             flash(f"'{policy_name}' ingested: {result['chunks']} chunks from {result['pages']} pages.", "success")
#         elif result["status"] == "already_ingested":
#             flash(f"'{policy_name}' already ingested ({result['chunks']} chunks).", "info")
#         else:
#             flash(f"Failed: {result.get('message', 'Unknown error')}", "error")
#     except Exception as e:
#         flash(f"Ingestion failed: {str(e)}", "error")

#     return redirect(url_for("policy"))


# @app.route("/policy/ask", methods=["POST"])
# def ask_policy():
#     policy_id = request.form.get("policy_id", "").strip()
#     question = request.form.get("question", "").strip()

#     if not policy_id:
#         flash("Please select a policy.", "error")
#         return redirect(url_for("policy"))
#     if not question:
#         flash("Please enter a question.", "error")
#         return redirect(url_for("policy"))

#     try:
#         policies = list_policies()
#         policy_name = "Unknown"
#         for p in policies:
#             if p["policy_id"] == policy_id:
#                 policy_name = p["policy_name"]
#                 break

#         result = query_policy(policy_id, question)
#         return render_template("policy_result.html",
#                                result=result, question=question,
#                                policy_name=policy_name, policy_id=policy_id)
#     except Exception as e:
#         flash(f"Query failed: {str(e)}", "error")
#         return redirect(url_for("policy"))


# @app.route("/policy/delete/<policy_id>", methods=["POST"])
# def remove_policy(policy_id):
#     if delete_policy(policy_id):
#         flash("Policy deleted.", "success")
#     else:
#         flash("Failed to delete policy.", "error")
#     return redirect(url_for("policy"))



# ============ NEGOTIATION AGENT ============
@app.route("/negotiate")
def negotiate():
    providers = get_providers()
    return render_template("negotiate.html", providers=providers)


@app.route("/negotiate/start", methods=["POST"])
def start_negotiation():
    try:
        current_premium = request.form.get("current_premium", "0")
        current_premium = int(current_premium) if current_premium.strip() else 0
        coverage_amount = request.form.get("coverage_amount", "0")
        coverage_amount = int(coverage_amount) if coverage_amount.strip() else 0
        tenure = request.form.get("tenure", "1")
        tenure = int(tenure) if tenure.strip() else 1
        age = request.form.get("age", "30")
        age = int(age) if age.strip() else 30
        ncb = request.form.get("ncb", "0")
        ncb = int(ncb) if ncb.strip() else 0
    except ValueError:
        flash("Please enter valid numeric values.", "error")
        return redirect(url_for("negotiate"))

    user_profile = {
        "insurance_type": request.form.get("insurance_type", "Motor"),
        "current_provider": request.form.get("current_provider", "").strip(),
        "current_premium": current_premium,
        "coverage_amount": coverage_amount,
        "tenure": tenure,
        "age": age,
        "city": request.form.get("city", "").strip(),
        "ncb": ncb,
        "notes": request.form.get("notes", "").strip(),
    }

    if not user_profile["current_provider"]:
        flash("Please enter your current provider.", "error")
        return redirect(url_for("negotiate"))
    if user_profile["current_premium"] <= 0:
        flash("Please enter a valid current premium.", "error")
        return redirect(url_for("negotiate"))
    if user_profile["coverage_amount"] <= 0:
        flash("Please enter a valid coverage / sum insured amount.", "error")
        return redirect(url_for("negotiate"))

    try:
        result = run_negotiation(user_profile)
        return render_template("negotiate_result.html", result=result)
    except json.JSONDecodeError:
        flash("AI returned invalid data. Please try again.", "error")
        return redirect(url_for("negotiate"))
    except Exception as e:
        flash(f"Negotiation failed: {str(e)}", "error")
        return redirect(url_for("negotiate"))
    



if __name__ == "__main__":
    app.run(debug=True, port=5000)