from flask import Flask, request, render_template
from app.config import Config

app = Flask(__name__)
config = Config()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        config.data["mqtt_broker"] = request.form["mqtt_broker"]
        config.data["mqtt_port"] = int(request.form["mqtt_port"])
        config.data["mqtt_topic"] = request.form["mqtt_topic"]
        config.data["mbus_port"] = request.form["mbus_port"]
        config.save()
    return render_template("index.html", config=config.data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
