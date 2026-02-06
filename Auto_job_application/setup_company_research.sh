#!/bin/bash

echo "========================================="
echo "Company Research Module - Setup Script"
echo "========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Please run this script from the Auto_job_application directory"
    exit 1
fi

echo "📦 Step 1: Installing Python dependencies..."
pip install pytrends>=4.9.2 yfinance>=0.2.0 flask>=3.0.0

echo ""
echo "🌐 Step 2: Installing Playwright browsers..."
playwright install chromium

echo ""
echo "✅ Setup complete!"
echo ""
echo "========================================="
echo "Next Steps:"
echo "========================================="
echo "1. Start the Flask app:"
echo "   python src/ui/app.py"
echo ""
echo "2. Open browser to:"
echo "   http://localhost:5000"
echo ""
echo "3. Navigate to 'Company Research' from the menu"
echo ""
echo "4. Test with a company like 'Razorpay' or 'Paytm'"
echo ""
echo "========================================="
