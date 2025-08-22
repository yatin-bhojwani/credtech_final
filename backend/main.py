import os
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import joblib
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import math
from datetime import timedelta
import shap

load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  
# CREDTECH_DIR = os.path.join(BASE_DIR, "../credtech")
MODEL_DIR = os.path.join(BASE_DIR, "models")

MODEL_PATH = os.path.join(MODEL_DIR, "credit_rating_model.joblib")
ENCODER_PATH = os.path.join(MODEL_DIR, "label_encoder.joblib")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.joblib")
CSV_PATH = os.path.join(MODEL_DIR, "sentiment.csv") 

def clean_nans(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(x) for x in obj]
    return obj

# loading the ml model
model = joblib.load(MODEL_PATH)
le = joblib.load(ENCODER_PATH)
scaler = joblib.load(SCALER_PATH)
df = pd.read_csv(CSV_PATH)   

try:
    explainer = shap.TreeExplainer(model)   
except Exception:
    explainer = shap.Explainer(model)      


def fetch_fred_series(series_id: str):
    url = f"{FRED_BASE_URL}?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    observations = data.get("observations", [])
    if not observations:
        return np.nan
    latest_value = observations[-1]["value"]
    return float(latest_value) if latest_value != "." else np.nan

def get_macro_features():
    gdp = fetch_fred_series("GDP")              #this is US GDP
    interest_rate = fetch_fred_series("FEDFUNDS")  

    # Inflation from CPI YoY
    cpi_url = f"{FRED_BASE_URL}?series_id=CPIAUCSL&api_key={FRED_API_KEY}&file_type=json"
    resp = requests.get(cpi_url)
    resp.raise_for_status()
    cpi_obs = resp.json().get("observations", [])
    if len(cpi_obs) < 13:
        inflation = np.nan
    else:
        latest_cpi = float(cpi_obs[-1]["value"])
        cpi_12mo_ago = float(cpi_obs[-13]["value"])
        inflation = ((latest_cpi - cpi_12mo_ago) / cpi_12mo_ago) * 100

    return gdp, interest_rate, inflation

def get_company_features(symbol: str, sentiment: float = 0.0):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    bs = ticker.balance_sheet

    # Ratios
    current_ratio = info.get("currentRatio", np.nan)
    quick_ratio = info.get("quickRatio", np.nan)

    try:
        cash = bs.loc["Cash"].iloc[0]
        curr_liab = bs.loc["Total Current Liabilities"].iloc[0]
        cash_ratio = cash / curr_liab
    except:
        cash_ratio = np.nan

    try:
        total_assets = bs.loc["Total Assets"].iloc[0]
        total_liab = bs.loc["Total Liab"].iloc[0]
        debt_ratio = total_liab / total_assets
    except:
        debt_ratio = np.nan

    debt_equity = info.get("debtToEquity", np.nan)

    
    hist = ticker.history(period="6mo")
    returns = hist["Close"].pct_change().dropna()
    volatility = returns.std() if not returns.empty else np.nan
    momentum = (
        (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]
        if len(hist) > 0 else np.nan
    )

    # this is macroeconomic data
    gdp, interest_rate, inflation = get_macro_features()

    features = [
        current_ratio, quick_ratio, cash_ratio, debt_ratio, debt_equity,
        gdp, interest_rate, inflation, volatility, momentum, sentiment
    ]
    return features


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def greet(name: str = "Guest"):
    return {"message": f"Hi {name}"}

@app.get("/company")
def get_company_data(symbol: str = Query(..., description="Ticker symbol, e.g. AAPL")):
    """
    Fetch real-time company features (Yahoo + FRED),
    run ML prediction for past 30 days, and return dashboard-ready output.
    """

    
    sentiment = 0.0
    company_row = df[df["company_name"].str.lower() == symbol.lower()]
    if not company_row.empty:
        sentiment = float(company_row.sort_values("rating_date").iloc[-1]["sentiment_proxy"])

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")  #for period of 6 months so volatility can be calculated

    
    gdp, interest_rate, inflation = get_macro_features()
    info = ticker.info
    bs = ticker.balance_sheet

    current_ratio = info.get("currentRatio", np.nan)
    quick_ratio = info.get("quickRatio", np.nan)
    try:
        cash = bs.loc["Cash"].iloc[0]
        curr_liab = bs.loc["Total Current Liabilities"].iloc[0]
        cash_ratio = cash / curr_liab
    except:
        cash_ratio = np.nan
    try:
        total_assets = bs.loc["Total Assets"].iloc[0]
        total_liab = bs.loc["Total Liab"].iloc[0]
        debt_ratio = total_liab / total_assets
    except:
        debt_ratio = np.nan
    debt_equity = info.get("debtToEquity", np.nan)

    static_features = [
        current_ratio, quick_ratio, cash_ratio, debt_ratio, debt_equity,
        gdp, interest_rate, inflation
    ]

    
    today = datetime.today().date()
    history = []

    for i in range(30, 0, -1):  
        day = today - timedelta(days=i)

        
        sub_hist = hist[hist.index.date <= day]
        if len(sub_hist) < 2:
            continue

        returns = sub_hist["Close"].pct_change().dropna()
        volatility = returns.std() if not returns.empty else np.nan
        momentum = (
            (sub_hist["Close"].iloc[-1] - sub_hist["Close"].iloc[0]) / sub_hist["Close"].iloc[0]
            if len(sub_hist) > 0 else np.nan
        )

        
        features = static_features + [volatility, momentum, sentiment]

        
        X_scaled = scaler.transform([features])
        pred = model.predict(X_scaled)
        predicted_label = le.inverse_transform(pred)[0]

        confidence = None
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_scaled)[0]
            confidence = float(np.max(probs))

        shap_values = explainer(X_scaled)
        shap_vals_raw = shap_values.values

        if isinstance(shap_vals_raw, list):
           shap_vals_vec = shap_vals_raw[pred[0]]
        else:
           shap_vals_vec = shap_vals_raw[0]

# this is mapping feature names -> shap values
        shap_vals_vec = np.array(shap_vals_vec).flatten()

        feature_names = ["currentRatio", "quickRatio", "cashRatio", "debtRatio", "debtEquityRatio",
                 "GDP", "INTEREST_RATE", "INFLATION", "volatility", "momentum", "sentiment"]

        contribs = dict(zip(feature_names, shap_vals_vec))

        top_contribs = sorted(contribs.items(), key=lambda x: abs(float(x[1])), reverse=True)[:3]
        all_contribs = sorted(contribs.items(), key=lambda x: abs(float(x[1])), reverse=True)
 

        history.append({
            "date": str(day),
            "predictedRating": int(predicted_label),
            "confidence": confidence,
            "top_features": [{"feature": f, "contribution": float(v)} for f, v in all_contribs]
        })

    response = {
        "symbol": symbol,
        "history": history,
        "features": {
            "currentRatio": current_ratio,
            "quickRatio": quick_ratio,
            "cashRatio": cash_ratio,
            "debtRatio": debt_ratio,
            "debtEquityRatio": debt_equity,
            "GDP": gdp,
            "INTEREST_RATE": interest_rate,
            "INFLATION": inflation,
            "sentiment": sentiment
        }
    }

    return clean_nans(response)
