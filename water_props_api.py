from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import CoolProp.CoolProp as CP
from scipy.optimize import brentq, fsolve

FLUID = "Water"

app = FastAPI(
    title="EasyTechCalculators – Water Properties API",
    description="Engineering-grade thermodynamic properties of water (ice, liquid, vapor)",
)

# =========================================================
# Models
# =========================================================

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
    viscosity: Optional[float]

# =========================================================
# Helpers
# =========================================================

def melting_temperature(P):
    """Melting temperature of ice-water at pressure P"""
    try:
        return CP.PropsSI("T", "P", P, "phase", "solid", FLUID)
    except:
        return 273.15

def detect_phase_PT(P, T):
    Tm = melting_temperature(P)
    Tsat = CP.PropsSI("T", "P", P, "Q", 0, FLUID)

    if T < Tm:
        return "ice"
    elif abs(T - Tsat) < 1e-3:
        return "saturated"
    elif T > Tsat:
        return "superheated_vapor"
    else:
        return "subcooled_liquid"

def prop(name, P, T):
    return CP.PropsSI(name, "P", P, "T", T, FLUID)

# =========================================================
# Solver Implementations
# =========================================================

def solve_PT(v1, v2):
    return (v1, v2)

def solve_Px(v1, v2):
    P = v1 if v1 > 1 else v2
    x = v2 if P == v1 else v1

    if not (0 <= x <= 1):
        raise HTTPException(400, "Quality must be between 0 and 1")

    T = CP.PropsSI("T", "P", P, "Q", x, FLUID)
    return P, T, x

def solve_Tx(v1, v2):
    T = v1 if v1 > 200 else v2
    x = v2 if T == v1 else v1

    if not (0 <= x <= 1):
        raise HTTPException(400, "Quality must be between 0 and 1")

    P = CP.PropsSI("P", "T", T, "Q", x, FLUID)
    return P, T, x

def solve_Ph(v1, v2):
    P = v1 if v1 > 1 else v2
    h_target = v2 if P == v1 else v1

    def f(T):
        return CP.PropsSI("H", "P", P, "T", T, FLUID) - h_target

    T = brentq(f, 250, 2000)
    return P, T

def solve_Ps(v1, v2):
    P = v1 if v1 > 1 else v2
    s_target = v2 if P == v1 else v1

    def f(T):
        return CP.PropsSI("S", "P", P, "T", T, FLUID) - s_target

    T = brentq(f, 250, 2000)
    return P, T

def solve_hs(h, s):
    def equations(vars):
        P, T = vars
        return [
            CP.PropsSI("H", "P", P, "T", T, FLUID) - h,
            CP.PropsSI("S", "P", P, "T", T, FLUID) - s,
        ]

    P0, T0 = 1e5, 500
    P, T = fsolve(equations, (P0, T0))
    return P, T

def solve_rhoT(v1, v2):
    rho = v1 if v1 > 1 else v2
    T = v2 if rho == v1 else v1

    def f(P):
        return CP.PropsSI("D", "P", P, "T", T, FLUID) - rho

    P = brentq(f, 1e3, 1e8)
    return P, T

# =========================================================
# Solver Dispatcher (YOUR TABLE)
# =========================================================

def dispatch_solver(n1, v1, n2, v2):
    pair = {n1, n2}

    if pair == {"P", "T"}:
        return (*solve_PT(v1, v2), None)

    if pair == {"P", "X"}:
        P, T, x = solve_Px(v1, v2)
        return P, T, x

    if pair == {"T", "X"}:
        P, T, x = solve_Tx(v1, v2)
        return P, T, x

    if pair == {"P", "H"}:
        return (*solve_Ph(v1, v2), None)

    if pair == {"P", "S"}:
        return (*solve_Ps(v1, v2), None)

    if pair == {"H", "S"}:
        return (*solve_hs(v1, v2), None)

    if pair == {"D", "T"}:
        return (*solve_rhoT(v1, v2), None)

    raise HTTPException(400, "Unsupported input pair")

# =========================================================
# Main Solver
# =========================================================

def solve_state(req: StateRequest):

    n1 = req.input1_name.upper()
    n2 = req.input2_name.upper()
    v1 = req.input1_value
    v2 = req.input2_value

    P, T, quality = dispatch_solver(n1, v1, n2, v2)

    phase = detect_phase_PT(P, T)

    if phase == "ice" and quality is not None:
        raise HTTPException(400, "Quality is not defined for ice")

    density = prop("D", P, T)

    return StateResponse(
        P=P,
        T=T,
        phase=phase,
        quality=quality,
        density=density,
        specific_volume=1 / density,
        cp=prop("Cpmass", P, T),
        cv=prop("Cvmass", P, T),
        entropy=prop("Smass", P, T),
        enthalpy=prop("Hmass", P, T),
        conductivity=prop("conductivity", P, T),
        viscosity=None if phase == "ice" else prop("viscosity", P, T),
    )

# =========================================================
# API Route
# =========================================================

@app.post("/water/state", response_model=StateResponse)
def water_state(req: StateRequest):
    return solve_state(req)
