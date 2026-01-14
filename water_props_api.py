from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import CoolProp.CoolProp as CP
from scipy.optimize import brentq

FLUID = "Water"

app = FastAPI(
    title="EasyTechCalculators – Water Properties API",
    description="Engineering-grade thermodynamic properties of water (IAPWS-IF97)",
)

# -----------------------------
# Models
# -----------------------------
class StateRequest(BaseModel):
    input1_name: str
    input1_value: float
    input2_name: str
    input2_value: float

class StateResponse(BaseModel):
    T: float
    P: float
    phase: str
    quality: Optional[float]
    density: float
    specific_volume: float
    cp: float
    cv: float
    entropy: float
    enthalpy: float
    conductivity: float
    viscosity: float

# -----------------------------
# Helpers
# -----------------------------
def sat_props_P(P, x):
    return CP.PropsSI("T", "P", P, "Q", x, FLUID)

def sat_props_T(T, x):
    return CP.PropsSI("P", "T", T, "Q", x, FLUID)

def detect_phase_PT(P, T):
    Tsat = CP.PropsSI("T", "P", P, "Q", 0, FLUID)
    if abs(T - Tsat) < 1e-3:
        return "saturated"
    elif T > Tsat:
        return "superheated_vapor"
    else:
        return "subcooled_liquid"

def prop(prop, P, T):
    return CP.PropsSI(prop, "P", P, "T", T, FLUID)

# -----------------------------
# Solver
# -----------------------------
def solve_state(req: StateRequest):

    n1, v1 = req.input1_name.upper(), req.input1_value
    n2, v2 = req.input2_name.upper(), req.input2_value

    quality = None

    # -------- Saturation with Quality --------
    if {n1, n2} == {"P", "X"}:
        P = v1 if n1 == "P" else v2
        quality = v1 if n1 == "X" else v2
        if not (0 <= quality <= 1):
            raise HTTPException(400, "Quality must be between 0 and 1")
        T = sat_props_P(P, quality)
        phase = "two_phase" if 0 < quality < 1 else "saturated"

    elif {n1, n2} == {"T", "X"}:
        T = v1 if n1 == "T" else v2
        quality = v1 if n1 == "X" else v2
        if not (0 <= quality <= 1):
            raise HTTPException(400, "Quality must be between 0 and 1")
        P = sat_props_T(T, quality)
        phase = "two_phase" if 0 < quality < 1 else "saturated"

    # -------- Direct --------
    elif {n1, n2} == {"P", "T"}:
        P = v1 if n1 == "P" else v2
        T = v1 if n1 == "T" else v2
        phase = detect_phase_PT(P, T)

    # -------- Inverse P + h --------
    elif {n1, n2} == {"P", "H"}:
        P = v1 if n1 == "P" else v2
        H_target = v1 if n1 == "H" else v2

        def f(T):
            return CP.PropsSI("H", "P", P, "T", T, FLUID) - H_target

        T = brentq(f, 273.15, 2000)
        phase = detect_phase_PT(P, T)

    # -------- Inverse P + s --------
    elif {n1, n2} == {"P", "S"}:
        P = v1 if n1 == "P" else v2
        S_target = v1 if n1 == "S" else v2

        def f(T):
            return CP.PropsSI("S", "P", P, "T", T, FLUID) - S_target

        T = brentq(f, 273.15, 2000)
        phase = detect_phase_PT(P, T)

    else:
        raise HTTPException(400, "Unsupported input combination")

    # -------- Properties --------
    density = prop("D", P, T)

    return StateResponse(
        T=T,
        P=P,
        phase=phase,
        quality=quality,
        density=density,
        specific_volume=1 / density,
        cp=prop("Cpmass", P, T),
        cv=prop("Cvmass", P, T),
        entropy=prop("Smass", P, T),
        enthalpy=prop("Hmass", P, T),
        conductivity=prop("conductivity", P, T),
        viscosity=prop("viscosity", P, T),
    )

@app.post("/water/state", response_model=StateResponse)
def water_state(req: StateRequest):
    return solve_state(req)
