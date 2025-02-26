from flask import Flask, jsonify, render_template
import requests
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import time

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for frontend requests

# Cache mechanism to reduce API calls
cache = {}
cache_timeout = 300  # seconds (5 minutes)

def get_cache(key):
    if key in cache:
        timestamp, data = cache[key]
        if time.time() - timestamp < cache_timeout:
            return data
    return None

def set_cache(key, data):
    cache[key] = (time.time(), data)

# Function to get NSE stock quote
def get_nse_quote(symbol):
    cache_key = f"nse_quote_{symbol}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.nseindia.com/",
    }

    session = requests.Session()

    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        response = session.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            return {"error": f"NSE API request failed ({response.status_code})"}

        data = response.json()
        
        # Extract relevant data
        quote_data = {
            "exchange": "NSE",
            "symbol": symbol,
            "name": data.get("info", {}).get("companyName", symbol),
            "price": data.get("priceInfo", {}).get("lastPrice"),
            "change": data.get("priceInfo", {}).get("change"),
            "changePercent": data.get("priceInfo", {}).get("pChange"),
            "open": data.get("priceInfo", {}).get("open"),
            "previousClose": data.get("priceInfo", {}).get("previousClose"),
            "dayHigh": data.get("priceInfo", {}).get("intraDayHighLow", {}).get("max"),
            "dayLow": data.get("priceInfo", {}).get("intraDayHighLow", {}).get("min"),
            "yearHigh": data.get("priceInfo", {}).get("yearHighLow", {}).get("max"),
            "yearLow": data.get("priceInfo", {}).get("yearHighLow", {}).get("min"),
            "volume": data.get("securityWiseDP", {}).get("quantityTraded"),
            "marketCap": data.get("securityInfo", {}).get("marketCap"),
        }
        
        set_cache(cache_key, quote_data)
        return quote_data

    except requests.exceptions.JSONDecodeError:
        return {"error": "Failed to parse NSE JSON response"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error fetching data from NSE: {str(e)}"}

# Function to get BSE stock quote using Yahoo Finance
def get_bse_quote(symbol):
    cache_key = f"bse_quote_{symbol}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    try:
        stock = yf.Ticker(f"{symbol}.BO")  # Yahoo Finance BSE format
        info = stock.info
        history = stock.history(period="2d")
        
        if history.empty or not info:
            return {"error": "Stock symbol not found or missing data"}
            
        # Calculate price change
        if len(history) >= 2:
            prev_close = history["Close"].iloc[-2]
            current_price = history["Close"].iloc[-1]
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
        else:
            change = 0
            change_percent = 0
            prev_close = current_price = history["Close"].iloc[-1]

        quote_data = {
            "exchange": "BSE",
            "symbol": symbol,
            "name": info.get("longName", symbol),
            "price": current_price,
            "change": change,
            "changePercent": change_percent,
            "open": info.get("regularMarketOpen", history["Open"].iloc[-1]),
            "previousClose": prev_close,
            "dayHigh": info.get("dayHigh", history["High"].iloc[-1]),
            "dayLow": info.get("dayLow", history["Low"].iloc[-1]),
            "yearHigh": info.get("fiftyTwoWeekHigh"),
            "yearLow": info.get("fiftyTwoWeekLow"),
            "volume": info.get("volume", history["Volume"].iloc[-1]),
            "marketCap": info.get("marketCap"),
        }
        
        set_cache(cache_key, quote_data)
        return quote_data

    except Exception as e:
        return {"error": f"Error fetching BSE data: {str(e)}"}

# Function to get NSE historical data including OHLC for candlestick
def get_nse_history(symbol, period):
    cache_key = f"nse_history_{symbol}_{period}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data
    
    # Convert to Yahoo Finance compatible format for both exchanges 
    yahoo_symbol = f"{symbol}.NS"
    
    try:
        # Map the period to Yahoo Finance format
        if period == "1d":
            interval = "5m"
            period_days = "1d"
        elif period == "1w":
            interval = "15m"
            period_days = "5d"
        elif period == "1m":
            interval = "1d"
            period_days = "1mo"
        elif period == "3m":
            interval = "1d"
            period_days = "3mo"
        elif period == "1y":
            interval = "1d"
            period_days = "1y"
        else:
            interval = "1d"
            period_days = "1mo"
            
        # Get data from Yahoo Finance
        stock = yf.Ticker(yahoo_symbol)
        df = stock.history(period=period_days, interval=interval)
        
        if df.empty:
            return {"error": "No historical data available"}
            
        # Format dates and extract price and volume
        dates = []
        prices = []
        volumes = []
        
        # For candlestick chart
        ohlc_data = []
        
        for index, row in df.iterrows():
            # Format date based on period
            if period == "1d" or period == "1w":
                date_str = index.strftime("%H:%M")
            else:
                date_str = index.strftime("%d/%m")
                
            dates.append(date_str)
            prices.append(row["Close"])
            volumes.append(int(row["Volume"]) if not pd.isna(row["Volume"]) else 0)
            
            # Add OHLC data for candlestick
            ohlc_data.append({
                "date": date_str,
                "timestamp": int(index.timestamp() * 1000),  # JavaScript timestamp (milliseconds)
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
            })
            
        history_data = {
            "dates": dates,
            "prices": prices,
            "volumes": volumes,
            "ohlc": ohlc_data  # Added OHLC data for candlestick
        }
        
        set_cache(cache_key, history_data)
        return history_data
        
    except Exception as e:
        return {"error": f"Error fetching NSE historical data: {str(e)}"}

# Function to get BSE historical data with OHLC
def get_bse_history(symbol, period):
    # Similar implementation as NSE, using Yahoo Finance
    cache_key = f"bse_history_{symbol}_{period}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data
    
    yahoo_symbol = f"{symbol}.BO"
    
    try:
        # Map the period to Yahoo Finance format (same as NSE function)
        if period == "1d":
            interval = "5m"
            period_days = "1d"
        elif period == "1w":
            interval = "15m"
            period_days = "5d"
        elif period == "1m":
            interval = "1d"
            period_days = "1mo"
        elif period == "3m":
            interval = "1d"
            period_days = "3mo"
        elif period == "1y":
            interval = "1d"
            period_days = "1y"
        else:
            interval = "1d"
            period_days = "1mo"
            
        # Get data from Yahoo Finance
        stock = yf.Ticker(yahoo_symbol)
        df = stock.history(period=period_days, interval=interval)
        
        if df.empty:
            return {"error": "No historical data available"}
            
        # Format dates and extract price and volume
        dates = []
        prices = []
        volumes = []
        
        # For candlestick chart
        ohlc_data = []
        
        for index, row in df.iterrows():
            # Format date based on period
            if period == "1d" or period == "1w":
                date_str = index.strftime("%H:%M")
            else:
                date_str = index.strftime("%d/%m")
                
            dates.append(date_str)
            prices.append(row["Close"])
            volumes.append(int(row["Volume"]) if not pd.isna(row["Volume"]) else 0)
            
            # Add OHLC data for candlestick
            ohlc_data.append({
                "date": date_str,
                "timestamp": int(index.timestamp() * 1000),  # JavaScript timestamp (milliseconds)
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
            })
            
        history_data = {
            "dates": dates,
            "prices": prices,
            "volumes": volumes,
            "ohlc": ohlc_data  # Added OHLC data for candlestick
        }
        
        set_cache(cache_key, history_data)
        return history_data
        
    except Exception as e:
        return {"error": f"Error fetching BSE historical data: {str(e)}"}

# API Route for stock quotes
@app.route('/<exchange>/<symbol>/quote', methods=['GET'])
def get_stock_quote(exchange, symbol):
    if exchange.lower() == 'nse':
        return jsonify(get_nse_quote(symbol.upper()))
    elif exchange.lower() == 'bse':
        return jsonify(get_bse_quote(symbol.upper()))
    else:
        return jsonify({"error": "Invalid exchange. Use 'nse' or 'bse'."})

# API Route for historical data
@app.route('/<exchange>/<symbol>/history/<period>', methods=['GET'])
def get_stock_history(exchange, symbol, period):
    if exchange.lower() == 'nse':
        return jsonify(get_nse_history(symbol.upper(), period))
    elif exchange.lower() == 'bse':
        return jsonify(get_bse_history(symbol.upper(), period))
    else:
        return jsonify({"error": "Invalid exchange. Use 'nse' or 'bse'."})

# Basic compatibility with original routes
@app.route('/nse/<symbol>', methods=['GET'])
def nse_price(symbol):
    data = get_nse_quote(symbol.upper())
    return jsonify({"exchange": "NSE", "symbol": symbol, "price": data.get("price")})

@app.route('/bse/<symbol>', methods=['GET'])
def bse_price(symbol):
    data = get_bse_quote(symbol.upper())
    return jsonify({"exchange": "BSE", "symbol": symbol, "price": data.get("price")})

# Home route to serve index.html
@app.route('/')
def home():
    return render_template('index.html')

# Run Flask app
if __name__ == '__main__':
    app.run(debug=True)