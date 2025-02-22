from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
load_dotenv()
import os
from google.generativeai import GenerativeModel
import google.generativeai as genai

app = Flask(__name__)

# Set your Gemini API key (replace with your actual key)
genai.configure(api_key="AIzaSyBGLep1-Ah7vc1-guR_1AqRPLu1zx7wGXk")

@app.route('/stock_advice', methods=['POST'])
def stock_advice():
    ticker = request.form.get('ticker')

    if not ticker:
        return jsonify({"error": "Ticker symbol is required."}), 400

    prompt = f"""
        Provide the following information for the stock with ticker symbol {ticker}:

        1. Stock Prediction (brief, 1-2 sentences, highly speculative, mention it's not financial advice)
        2. Best Time to Invest (brief, general advice, mention it depends on individual circumstances)
        3. Merits of the Stock (3-4 points)
        4. Demerits of the Stock (3-4 points)

        Important: All information provided should be for casual informational purposes only and NOT financial advice.  Emphasize that users must do their own research and consult with a financial advisor before making any investment decisions.
        """

    try:
        model = GenerativeModel(
            model_name="gemini-pro",  # Or the model you want to use
        )
        response = model.generate_content(prompt)
        advice = response.text
        return jsonify({"advice": advice})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return render_template('Beginners_tutorial.html')  # Your existing template

if __name__ == '__main__':
    app.run(debug=True)