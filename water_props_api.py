from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import CoolProp.CoolProp as CP

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FLUID = "Water"

class StateRequest(BaseModel):
    input1_name: str
    input1_value: float
    input2_name: str
    input2_value: float

def melting_temperature(P):
    return CP.PropsSI("T", "P", P, "Q", 0, FLUID)

def detect_phase_PT(P, T):
    Tsat = CP.PropsSI("T", "P", P, "Q", 0, FLUID)
    Tm = melting_temperature(P)

    if T < Tm:
        return "ice"
    elif abs(T - Tsat) < 1e-2:
        return "two-phase"
    elif T > Tsat:
        return "superheated_vapor"
    else:
        return "subcooled_liquid"

def get_all_properties(P, T, phase, quality=None):
    props = {}

    props["density"] = CP.PropsSI("D", "P", P, "T", T, FLUID)
    props["specific_volume"] = 1 / props["density"]
    props["Cp"] = CP.PropsSI("C", "P", P, "T", T, FLUID)
    props["Cv"] = CP.PropsSI("O", "P", P, "T", T, FLUID)
    props["entropy"] = CP.PropsSI("S", "P", P, "T", T, FLUID)
    props["enthalpy"] = CP.PropsSI("H", "P", P, "T", T, FLUID)
    props["thermal_conductivity"] = CP.PropsSI("L", "P", P, "T", T, FLUID)
    props["viscosity"] = CP.PropsSI("V", "P", P, "T", T, FLUID)

    if phase == "two-phase":
        if quality is not None:
            props["quality"] = quality
        else:
            # Compute quality from enthalpy (safe method)
            hf = CP.PropsSI("H", "P", P, "Q", 0, FLUID)
            hg = CP.PropsSI("H", "P", P, "Q", 1, FLUID)
            props["quality"] = (props["enthalpy"] - hf) / (hg - hf)

    props["phase"] = phase
    return props

def solve_state(i1, v1, i2, v2):
    i1 = i1.upper()
    i2 = i2.upper()
    inputs = {i1: v1, i2: v2}

    try:
        # -----------------------------
        # Temperature + Quality
        # -----------------------------
        if "T" in inputs and "X" in inputs:
            T = inputs["T"]
            X = inputs["X"]
            P = CP.PropsSI("P", "T", T, "Q", X, FLUID)
            phase = "two-phase"
            return get_all_properties(P, T, phase, quality=X)

        # -----------------------------
        # Pressure + Quality
        # -----------------------------
        if "P" in inputs and "X" in inputs:
            P = inputs["P"]
            X = inputs["X"]
            T = CP.PropsSI("T", "P", P, "Q", X, FLUID)
            phase = "two-phase"
            return get_all_properties(P, T, phase, quality=X)

        # -----------------------------
        # Temperature + Pressure
        # -----------------------------
        if "T" in inputs and "P" in inputs:
            T = inputs["T"]
            P = inputs["P"]
            phase = detect_phase_PT(P, T)
            return get_all_properties(P, T, phase)

        # -----------------------------
        # Pressure + Enthalpy
        # -----------------------------
        if "P" in inputs and "H" in inputs:
            P = inputs["P"]
            H = inputs["H"]
            T = CP.PropsSI("T", "P", P, "H", H, FLUID)
            phase = detect_phase_PT(P, T)
            return get_all_properties(P, T, phase)

        # -----------------------------
        # Temperature + Enthalpy
        # -----------------------------
        if "T" in inputs and "H" in inputs:
            T = inputs["T"]
            H = inputs["H"]
            P = CP.PropsSI("P", "T", T, "H", H, FLUID)
            phase = detect_phase_PT(P, T)
            return get_all_properties(P, T, phase)

        # -----------------------------
        # Pressure + Entropy
        # -----------------------------
        if "P" in inputs and "S" in inputs:
            P = inputs["P"]
            S = inputs["S"]
            T = CP.PropsSI("T", "P", P, "S", S, FLUID)
            phase = detect_phase_PT(P, T)
            return get_all_properties(P, T, phase)

        # -----------------------------
        # Temperature + Entropy
        # -----------------------------
        if "T" in inputs and "S" in inputs:
            T = inputs["T"]
            S = inputs["S"]
            P = CP.PropsSI("P", "T", T, "S", S, FLUID)
            phase = detect_phase_PT(P, T)
            return get_all_properties(P, T, phase)

        raise ValueError("Unsupported input pair")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/water/state")
def water_state(req: StateRequest):
    return solve_state(
        req.input1_name,
        req.input1_value,
        req.input2_name,
        req.input2_value
    )
