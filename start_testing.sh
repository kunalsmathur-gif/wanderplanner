#!/bin/bash

echo "🚀 WanderPlanner E2E Testing Setup"
echo "================================"
echo ""

# Check frontend
echo "✅ Checking Frontend (Next.js)..."
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "   ✓ Frontend running at http://localhost:3000"
else
    echo "   ✗ Frontend not running. Starting..."
    cd apps/web && npm run dev > /tmp/nextjs.log 2>&1 &
    echo "   ⏳ Waiting for frontend to start..."
    sleep 10
fi

# Check backend
echo ""
echo "✅ Checking Backend API..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✓ Backend running at http://localhost:8000"
else
    echo "   ✗ Backend not running. Please start it manually:"
    echo "      cd apps/api && uvicorn main:app --reload --port 8000"
fi

echo ""
echo "📊 Server Status:"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8000"
echo "   Health:   $(curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo 'Not available')"

echo ""
echo "🎬 Start Screen Recording:"
echo "   1. Press Cmd + Shift + 5"
echo "   2. Select 'Record Entire Screen' or 'Record Selected Portion'"
echo "   3. Click the Record button"
echo ""
echo "📖 Testing Guide: wanderplanner/E2E_TESTING_GUIDE.md"
echo ""
echo "🌐 Opening browser..."
sleep 2
open http://localhost:3000

echo ""
echo "✨ Ready to test! Press Cmd + Shift + 5 to start recording."
