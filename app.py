from flask import Flask, jsonify, render_template, request
import requests
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import time
import google.generativeai as genai

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for frontend requests

# Configure Gemini API
genai.configure(api_key="AIzaSyAN5LdfkT3LvOsZefvNaE2OuLo7ugl-2-c")  # Replace with actual API key in production
gemini_model = genai.GenerativeModel('gemini-1.5-pro')

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
            prices.append(float(row["Close"]))
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
            prices.append(float(row["Close"]))
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

# Function to get AI insights using Gemini API
def get_ai_insights(symbol, exchange, stock_data, history_data):
    cache_key = f"ai_insights_{symbol}_{exchange}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data
    
    try:
        # Prepare stock data summary with safe type conversion
        current_price = float(stock_data.get("price", 0)) if stock_data.get("price") is not None else "N/A"
        prev_close = float(stock_data.get("previousClose", 0)) if stock_data.get("previousClose") is not None else "N/A"
        day_high = float(stock_data.get("dayHigh", 0)) if stock_data.get("dayHigh") is not None else "N/A"
        day_low = float(stock_data.get("dayLow", 0)) if stock_data.get("dayLow") is not None else "N/A"
        year_high = float(stock_data.get("yearHigh", 0)) if stock_data.get("yearHigh") is not None else "N/A"
        year_low = float(stock_data.get("yearLow", 0)) if stock_data.get("yearLow") is not None else "N/A"
        volume = stock_data.get("volume", "N/A")
        change_percent = float(stock_data.get("changePercent", 0)) if stock_data.get("changePercent") is not None else "N/A"
        
        # Calculate some technical indicators if history data available
        technical_signals = []
        if (history_data and "prices" in history_data and 
            len(history_data["prices"]) > 14 and 
            isinstance(current_price, (int, float))):
            
            prices = history_data["prices"]
            # Simple Moving Average (SMA) 5-day and 14-day
            sma5 = sum(prices[-5:]) / 5 if len(prices) >= 5 else None
            sma14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else None
            
            if sma5 and sma14:
                if sma5 > sma14:
                    technical_signals.append("Short-term SMA above long-term SMA (bullish)")
                else:
                    technical_signals.append("Short-term SMA below long-term SMA (bearish)")
                    
            # Price relative to SMA
            if sma14 and current_price > sma14:
                technical_signals.append("Price above 14-day SMA (bullish)")
            elif sma14:
                technical_signals.append("Price below 14-day SMA (bearish)")
                
            # Check if price near support/resistance
            if (isinstance(year_low, (int, float)) and 
                year_low > 0 and 
                current_price < (year_low * 1.05)):
                technical_signals.append("Price near yearly support")
                
            if (isinstance(year_high, (int, float)) and 
                year_high > 0 and 
                current_price > (year_high * 0.95)):
                technical_signals.append("Price near yearly resistance")
        
        # Format values for display in the prompt
        current_price_str = f"₹{current_price}" if isinstance(current_price, (int, float)) else current_price
        prev_close_str = f"₹{prev_close}" if isinstance(prev_close, (int, float)) else prev_close
        day_high_str = f"₹{day_high}" if isinstance(day_high, (int, float)) else day_high
        day_low_str = f"₹{day_low}" if isinstance(day_low, (int, float)) else day_low
        year_high_str = f"₹{year_high}" if isinstance(year_high, (int, float)) else year_high
        year_low_str = f"₹{year_low}" if isinstance(year_low, (int, float)) else year_low
        change_percent_str = f"{change_percent}%" if isinstance(change_percent, (int, float)) else change_percent
        
        # Construct a prompt for Gemini
        prompt = f"""
        Analyze the following Indian stock ({exchange}:{symbol}) based on the provided data:
        
        Current Price: {current_price_str}
        Previous Close: {prev_close_str}
        Day Range: {day_low_str} - {day_high_str}
        52-Week Range: {year_low_str} - {year_high_str}
        Change %: {change_percent_str}
        Volume: {volume}
        
        Technical Indicators:
        {', '.join(technical_signals) if technical_signals else 'No technical indicators available'}
        
        Based on current market conditions and recent news, provide a concise analysis with:
        1. Key strengths (merits) of investing in this stock
        2. Potential risks (demerits)
        3. Technical analysis recommendation (buy, sell, or hold)
        4. Fundamental analysis insights
        5. Ideal entry and exit price points, if applicable
        
        Format your response as clear sections. Keep the analysis concise but insightful.
        enclose all the bold words and characters in <b></b> tags.
        instead of using stars for points, enclose them in <ul></ul> tags.
        """
        
        # Call Gemini API
        response = gemini_model.generate_content(prompt)
        
        # Parse and structure the response
        insights = {
            "analysis": response.text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        set_cache(cache_key, insights)
        return insights
        
    except Exception as e:
        return {"error": f"Error generating AI insights: {str(e)}"}

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

# API Route for AI insights
@app.route('/<exchange>/<symbol>/insights', methods=['GET'])
def get_stock_insights(exchange, symbol):
    if exchange.lower() not in ('nse', 'bse'):
        return jsonify({"error": "Invalid exchange. Use 'nse' or 'bse'."})
    
    symbol = symbol.upper()
    
    # Get stock data
    if exchange.lower() == 'nse':
        stock_data = get_nse_quote(symbol)
    else:
        stock_data = get_bse_quote(symbol)
    
    if "error" in stock_data:
        return jsonify({"error": f"Could not get stock data: {stock_data['error']}"})
    
    # Get historical data (1 month for analysis)
    if exchange.lower() == 'nse':
        history_data = get_nse_history(symbol, "1m")
    else:
        history_data = get_bse_history(symbol, "1m")
    
    # Get AI insights
    insights = get_ai_insights(symbol, exchange, stock_data, history_data)
    
    return jsonify(insights)

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