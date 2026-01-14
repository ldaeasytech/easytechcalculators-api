from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import CoolProp.CoolProp as CP
from scipy.optimize import brentq

FLUID = "Water"

app = FastAPI(title="EasyTechCalculators Water Properties API")

# -----------------------------
# Request / Response Models
# -----------------------------
class StateRequest(BaseModel):
    input1_name: str
    input1_value: float
    input2_name: str
    input2_value: float
    phase: Optional[str] = None

class StateResponse(BaseModel):
    T: float
    P: float
    phase: str
    density: float
    specific_volume: float
    cp: float
    cv: float
    entropy: float
    enthalpy: float
    conductivity: float
    viscosity: float

# -----------------------------
# Helper Functions
# -----------------------------
def prop(prop, P, T):
    return CP.PropsSI(prop, "P", P, "T", T, FLUID)

def detect_phase(P, T):
    Tsat = CP.PropsSI("T", "P", P, "Q", 0, FLUID)
    if abs(T - Tsat) < 1e-3:
        return "saturated"
    elif T > Tsat:
        return "superheated_vapor"
    else:
        return "subcooled_liquid"

# -----------------------------
# Solver
# -----------------------------
def solve_state(req: StateRequest):
    n1, v1 = req.input1_name.upper(), req.input1_value
    n2, v2 = req.input2_name.upper(), req.input2_value

    if {n1, n2} == {"T", "P"}:
        T = v1 if n1 == "T" else v2
        P = v1 if n1 == "P" else v2

    elif {n1, n2} == {"P", "H"}:
        P = v1 if n1 == "P" else v2
        H_target = v1 if n1 == "H" else v2

        def f(T):
            return CP.PropsSI("H", "P", P, "T", T, FLUID) - H_target

        T = brentq(f, 273.15, 2000)

    elif {n1, n2} == {"P", "S"}:
        P = v1 if n1 == "P" else v2
        S_target = v1 if n1 == "S" else v2

        def f(T):
            return CP.PropsSI("S", "P", P, "T", T, FLUID) - S_target

        T = brentq(f, 273.15, 2000)

    else:
        raise HTTPException(400, "Input pair not supported yet")

    phase = detect_phase(P, T)

    density = prop("D", P, T)

    return StateResponse(
        T=T,
        P=P,
        phase=phase,
        density=density,
        specific_volume=1.0 / density,
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

