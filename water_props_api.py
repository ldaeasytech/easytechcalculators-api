from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import CoolProp.CoolProp as CP
from scipy.optimize import brentq

FLUID = "Water"

app = FastAPI(
    title="EasyTechCalculators – Water Properties API",
    description="Engineering-grade thermodynamic properties of water"
)

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://easytechcalculators.com",
        "https://www.easytechcalculators.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# MODELS
# =========================
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
    cp: float
    cv: float
    entropy: float
    enthalpy: float
    conductivity: float
    viscosity: Optional[float]

# =========================
# HELPERS
# =========================
def melting_temperature(P):
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

# =========================
# SOLVER DISPATCHER
# =========================
def solve_state(i1, v1, i2, v2):
    inputs = {i1.upper(): v1, i2.upper(): v2}

    try:
        # T + P
        if "T" in inputs and "P" in inputs:
            T, P = inputs["T"], inputs["P"]

        # P + x
        elif "P" in inputs and "X" in inputs:
            P = inputs["P"]
            x = inputs["X"]
            if not (0 <= x <= 1):
                raise ValueError("Quality must be between 0 and 1.")
            T = CP.PropsSI("T", "P", P, "Q", x, FLUID)

        # T + x
        elif "T" in inputs and "X" in inputs:
            T = inputs["T"]
            x = inputs["X"]
            if not (0 <= x <= 1):
                raise ValueError("Quality must be between 0 and 1.")
            P = CP.PropsSI("P", "T", T, "Q", x, FLUID)

        # P + h
        elif "P" in inputs and "H" in inputs:
            P, h = inputs["P"], inputs["H"]
            T = brentq(
                lambda T_: CP.PropsSI("H", "P", P, "T", T_, FLUID) - h,
                250, 2000
            )

        # P + s
        elif "P" in inputs and "S" in inputs:
            P, s = inputs["P"], inputs["S"]
            T = brentq(
                lambda T_: CP.PropsSI("S", "P", P, "T", T_, FLUID) - s,
                250, 2000
            )

        # h + s
        elif "H" in inputs and "S" in inputs:
            h, s = inputs["H"], inputs["S"]
            T = brentq(
                lambda T_: CP.PropsSI("H", "T", T_, "S", s, FLUID) - h,
                250, 2000
            )
            P = CP.PropsSI("P", "T", T, "S", s, FLUID)

        # rho + T
        elif "D" in inputs and "T" in inputs:
            rho, T = inputs["D"], inputs["T"]
            P = CP.PropsSI("P", "T", T, "D", rho, FLUID)

        else:
            raise ValueError(f"Unsupported input pair: {i1} + {i2}")

        phase = detect_phase_PT(P, T)

        Q = None
        if phase == "saturated":
            Q = CP.PropsSI("Q", "P", P, "T", T, FLUID)

        return {
            "T": T,
            "P": P,
            "phase": phase,
            "quality": Q,
            "density": CP.PropsSI("D", "T", T, "P", P, FLUID),
            "cp": CP.PropsSI("Cpmass", "T", T, "P", P, FLUID),
            "cv": CP.PropsSI("Cvmass", "T", T, "P", P, FLUID),
            "entropy": CP.PropsSI("Smass", "T", T, "P", P, FLUID),
            "enthalpy": CP.PropsSI("Hmass", "T", T, "P", P, FLUID),
            "conductivity": CP.PropsSI("L", "T", T, "P", P, FLUID),
            "viscosity": CP.PropsSI("V", "T", T, "P", P, FLUID)
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# =========================
# API ROUTE
# =========================
@app.post("/water/state", response_model=StateResponse)
def water_state(req: StateRequest):
    return solve_state(
        req.input1_name,
        req.input1_value,
        req.input2_name,
        req.input2_value
    )
