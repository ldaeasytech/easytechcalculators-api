from flask import Flask, request, jsonify
from flask_cors import CORS
import CoolProp.CoolProp as CP

app = Flask(__name__)
CORS(app)

FLUID = "Water"

@app.route("/api/water", methods=["POST"])
def water_api():
    try:
        data = request.json
        unit = data.get("unit", "SI")
        pair = data.get("pair")
        v1 = float(data.get("v1"))
        v2 = float(data.get("v2"))

        # --- Unit conversions to SI ---
        if unit == "ENG":
            # Temperature °F → K
            if pair in ["PT", "Tx", "rhoT"]:
                v1 = (v1 - 32) * 5/9 + 273.15
            # Pressure psia → Pa
            if pair in ["PT", "Px", "Ph", "Ps"]:
                v1 = v1 * 6894.757
            # Enthalpy Btu/lbm → J/kg
            if pair in ["Ph", "hs"]:
                v2 = v2 * 2326
            # Entropy Btu/lbm-R → J/kg-K
            if pair in ["Ps", "hs"]:
                v2 = v2 * 4186.8
            # Density lbm/ft³ → kg/m³
            if pair == "rhoT":
                v1 = v1 * 16.0185

        # --- Determine state ---
        if pair == "PT":
            T, P = v1, v2
        elif pair == "Px":
            P, x = v1, v2
            T = CP.PropsSI("T", "P", P, "Q", x, FLUID)
        elif pair == "Tx":
            T, x = v1, v2
            P = CP.PropsSI("P", "T", T, "Q", x, FLUID)
        elif pair == "Ph":
            P, h = v1, v2 * 1000
            T = CP.PropsSI("T", "P", P, "H", h, FLUID)
        elif pair == "Ps":
            P, s = v1, v2 * 1000
            T = CP.PropsSI("T", "P", P, "S", s, FLUID)
        elif pair == "hs":
            h = v1 * 1000
            s = v2 * 1000
            T = CP.PropsSI("T", "H", h, "S", s, FLUID)
            P = CP.PropsSI("P", "H", h, "S", s, FLUID)
        elif pair == "rhoT":
            rho, T = v1, v2
            P = CP.PropsSI("P", "D", rho, "T", T, FLUID)
        else:
            return jsonify({"error": "Invalid input pair"}), 400

        # --- Calculate properties ---
        results = {
            "T": CP.PropsSI("T", "T", T, "P", P, FLUID),
            "P": CP.PropsSI("P", "T", T, "P", P, FLUID),
            "rho": CP.PropsSI("D", "T", T, "P", P, FLUID),
            "v": 1 / CP.PropsSI("D", "T", T, "P", P, FLUID),
            "h": CP.PropsSI("H", "T", T, "P", P, FLUID),
            "s": CP.PropsSI("S", "T", T, "P", P, FLUID),
            "cp": CP.PropsSI("C", "T", T, "P", P, FLUID),
            "cv": CP.PropsSI("O", "T", T, "P", P, FLUID),
            "k": CP.PropsSI("L", "T", T, "P", P, FLUID),
            "mu": CP.PropsSI("VISCOSITY", "T", T, "P", P, FLUID)
        }

        # --- Convert outputs to user units ---
        if unit == "ENG":
            results["T"] = (results["T"] - 273.15) * 9/5 + 32
            results["P"] = results["P"] / 6894.757
            results["h"] = results["h"] / 2326
            results["s"] = results["s"] / 4186.8
            results["cp"] = results["cp"] / 4186.8
            results["cv"] = results["cv"] / 4186.8
            results["rho"] = results["rho"] / 16.0185
            results["v"] = results["v"] * 16.0185

        # --- Region detection ---
        T_sat = CP.PropsSI("T", "P", results["P"] * (6894.757 if unit == "ENG" else 1), "Q", 0, FLUID)
        if abs(T - T_sat) < 0.1:
            region = "Two-Phase"
        elif T < 273.15:
            region = "Ice"
        elif T > T_sat:
            region = "Superheated Steam"
        else:
            region = "Subcooled Liquid"

        return jsonify({
            "success": True,
            "region": region,
            "results": results
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
