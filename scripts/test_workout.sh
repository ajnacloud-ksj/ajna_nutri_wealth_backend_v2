#!/bin/bash
API_URL="http://localhost:8000"

echo "=== Testing Workout Analysis ==="

# Minimal test workout description
DESC="Workout: Bench Press 3 sets of 10 reps at 135 lbs, Squats 4 sets of 8 reps at 185 lbs"

cat <<EOF > payload_workout.json
{
  "description": "$DESC"
}
EOF

echo "Sending workout analysis request..."
RESP=$(curl -s -X POST "$API_URL/v1/analyze" \
  -H "Content-Type: application/json" \
  -d @payload_workout.json)

echo "Response: $RESP"

ENTRY_ID=$(echo "$RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('entry_id', ''))" 2>/dev/null)

if [ -z "$ENTRY_ID" ]; then
    echo "❌ Failed to create workout"
    exit 1
fi

echo "✅ Workout created with ID: $ENTRY_ID"

# Check if exercises were created
echo ""
echo "Checking workout exercises..."
sleep 2

python3 -c "
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.append('backend/src')

from lib.ibex_client import IbexClient

api_url = os.environ.get('IBEX_API_URL')
api_key = os.environ.get('IBEX_API_KEY')
client = IbexClient(api_url, api_key, 'test-tenant', 'default')

# Query workout
result = client.query('app_workouts', filters=[{'field': 'id', 'operator': 'eq', 'value': '$ENTRY_ID'}], limit=1)
if result.get('success'):
    workouts = result.get('data', {}).get('records', [])
    if workouts:
        workout = workouts[0]
        print(f\"✅ Workout found: {workout.get('workout_type')} - Duration: {workout.get('duration_minutes')} min\")
    else:
        print('❌ Workout not found')
else:
    print('❌ Query failed')

# Query exercises
ex_result = client.query('app_workout_exercises', filters=[{'field': 'workout_id', 'operator': 'eq', 'value': '$ENTRY_ID'}], limit=10)
if ex_result.get('success'):
    exercises = ex_result.get('data', {}).get('records', [])
    print(f\"✅ Found {len(exercises)} exercises:\")
    for ex in exercises:
        print(f\"   - {ex.get('exercise_name')}: {ex.get('sets')} sets x {ex.get('reps')} reps @ {ex.get('weight')} lbs\")
else:
    print('❌ Exercises query failed')
"

rm payload_workout.json
