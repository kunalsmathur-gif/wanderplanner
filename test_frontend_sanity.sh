#!/usr/bin/env bash
set -euo pipefail

echo "==================================="
echo "  WanderPlan Frontend Sanity Check"
echo "==================================="
echo ""

cd "$(dirname "$0")/apps/web"

# 1. Check for common React issues in code
echo "1. Checking for potential React issues..."
echo "   - Searching for nested buttons..."
grep -rn "button.*button" components/ 2>/dev/null && echo "⚠️  Found potential nested buttons" || echo "✅ No nested buttons found"

echo "   - Checking for missing keys in .map()..."
grep -rn "\.map(" components/ | grep -v "key=" | head -5 && echo "⚠️  Potential missing keys" || echo "✅ Keys look good"

echo "   - Checking for console.log statements..."
CONSOLE_LOGS=$(grep -rn "console\.log" components/ 2>/dev/null | wc -l | tr -d ' ')
echo "   Found $CONSOLE_LOGS console.log statements"
[ "$CONSOLE_LOGS" -gt 10 ] && echo "⚠️  Consider removing some console.logs"

echo ""

# 2. Check TypeScript compilation
echo "2. Running TypeScript check..."
npm run build 2>&1 | tail -20
BUILD_STATUS=$?
if [ $BUILD_STATUS -eq 0 ]; then
    echo "✅ TypeScript compilation successful"
else
    echo "❌ TypeScript compilation failed"
    exit 1
fi

echo ""

# 3. Check for large bundle issues
echo "3. Checking bundle size..."
if [ -d ".next" ]; then
    echo "✅ Build directory exists"
    echo "   Route sizes:"
    find .next -name "*.js" -type f | head -10 | while read file; do
        size=$(du -h "$file" | cut -f1)
        echo "   - $(basename $file): $size"
    done
fi

echo ""

# 4. Check for accessibility issues in components
echo "4. Basic accessibility checks..."
echo "   - Checking for alt text on images..."
grep -rn "<img" components/ | grep -v "alt=" && echo "⚠️  Images without alt text found" || echo "✅ All images have alt text"

echo "   - Checking for aria-label on buttons..."
BUTTONS_COUNT=$(grep -rn "<button" components/ 2>/dev/null | wc -l | tr -d ' ')
ARIA_COUNT=$(grep -rn "aria-label" components/ 2>/dev/null | wc -l | tr -d ' ')
echo "   Found $BUTTONS_COUNT buttons, $ARIA_COUNT have aria-labels"

echo ""

# 5. Check for hardcoded values that should be environment variables
echo "5. Checking for hardcoded URLs..."
grep -rn "http://localhost" components/ lib/ 2>/dev/null | wc -l | tr -d ' ' | {
    read count
    if [ "$count" -gt 0 ]; then
        echo "⚠️  Found $count hardcoded localhost URLs"
    else
        echo "✅ No hardcoded localhost URLs"
    fi
}

echo ""

# 6. Check for proper error boundaries
echo "6. Checking for error handling..."
grep -rn "try.*catch" components/ 2>/dev/null | wc -l | tr -d ' ' | {
    read count
    echo "   Found $count try-catch blocks"
    [ "$count" -lt 5 ] && echo "⚠️  Consider adding more error handling"
}

echo ""

echo "==================================="
echo "  Sanity Check Complete!"
echo "==================================="
