#this is just a test file
import yfinance as yf
import numpy as np
import requests
import os
from dotenv import load_dotenv

load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")  
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

def fetch_fred_series(series_id: str):
    """Fetch the latest value from a FRED series."""
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
    """Fetch GDP, Interest Rate, and Inflation from FRED."""
    gdp = fetch_fred_series("GDP")  
    interest_rate = fetch_fred_series("FEDFUNDS")  
    
    
    cpi_data_url = f"{FRED_BASE_URL}?series_id=CPIAUCSL&api_key={FRED_API_KEY}&file_type=json"
    resp = requests.get(cpi_data_url)
    resp.raise_for_status()
    cpi_obs = resp.json().get("observations", [])
    if len(cpi_obs) < 13:
        inflation = np.nan
    else:
        latest_cpi = float(cpi_obs[-1]["value"])
        cpi_12mo_ago = float(cpi_obs[-13]["value"])
        inflation = ((latest_cpi - cpi_12mo_ago) / cpi_12mo_ago) * 100

    return gdp, interest_rate, inflation


def get_company_features(symbol: str, gdp: float, interest_rate: float, inflation: float, sentiment: float):
    ticker = yf.Ticker(symbol)

    info = ticker.info
    bs = ticker.balance_sheet

    
    current_ratio = info.get("currentRatio", np.nan)
    quick_ratio = info.get("quickRatio", np.nan)

    
    try:
        cash = bs.loc["Cash"][0]
        curr_liab = bs.loc["Total Current Liabilities"][0]
        cash_ratio = cash / curr_liab
    except:
        cash_ratio = np.nan

    
    try:
        
          total_assets = bs.loc["Total Assets"].iloc[0]
          curr_liab = bs.loc["Total Current Liabilities"].iloc[0]
          cash = bs.loc["Cash"].iloc[0]
          total_liab = bs.loc["Total Liab"].iloc[0]
    except:
        debt_ratio = np.nan

    
    debt_equity = info.get("debtToEquity", np.nan)

    
    hist = ticker.history(period="6mo")
    returns = hist["Close"].pct_change().dropna()

    volatility = returns.std()
    momentum = (
    (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]
    if len(hist) > 0 else np.nan
     )


    
    features = [
        current_ratio,
        quick_ratio,
        cash_ratio,
        debt_ratio,
        debt_equity,
        gdp,
        interest_rate,
        inflation,
        volatility,
        momentum,
        sentiment
    ]

    return features


if __name__ == "__main__":
    # this is for fetching macro features from FRED
    GDP, INTEREST_RATE, INFLATION = get_macro_features()
    SENTIMENT = 0  

    symbol = "JBHT" #i took some random company
    features = get_company_features(symbol, GDP, INTEREST_RATE, INFLATION, SENTIMENT)

    print(f"Features for {symbol}:")
    for name, value in zip([
        "currentRatio", "quickRatio", "cashRatio", "debtRatio", "debtEquityRatio",
        "GDP", "INTEREST_RATE", "INFLATION", "volatility", "momentum", "sentiment_proxy"
    ], features):
        print(f"{name:20s}: {value}")
