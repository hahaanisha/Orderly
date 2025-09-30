from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import time
import random

app = Flask(__name__)


# Google Sheets setup
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS = Credentials.from_service_account_file('recroot-66242-feb07aaf9ef6.json', scopes=SCOPE)
CLIENT = gspread.authorize(CREDS)
SHEET_ID = '18Z5y8_pNa-v-voCeo3CzKg21t1KixLZi2bC0G9eAAlw'
SHEET = CLIENT.open_by_key(SHEET_ID)

# Helper functions
def get_sheet_data(tab_name):
    return SHEET.worksheet(tab_name).get_all_records()

def append_to_sheet(tab_name, data):
    SHEET.worksheet(tab_name).append_row(list(data.values()))

def update_sheet_cell(tab_name, row_idx, col_name, value):
    worksheet = SHEET.worksheet(tab_name)
    col_idx = worksheet.row_values(1).index(col_name) + 1
    worksheet.update_cell(row_idx + 2, col_idx, value)  # +2 for header row

# GET /orders/{order_id}
@app.route('/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    if random.random() < 0.1:  # 10% chance of timeout
        time.sleep(6)
        return jsonify({"error_code": 503, "message": "Service unavailable"}), 503
    data = get_sheet_data('Orders')
    order = next((row for row in data if row['order_id'] == order_id), None)
    if not order:
        return jsonify({"error_code": 404, "message": "Order not found"}), 404
    # Mask PII
    order['email'] = order['email'][:1] + '***' + order['email'][order['email'].find('@'):]
    order['phone'] = '***-***-' + order['phone'][-4:]
    return jsonify(order)

# POST /refunds
@app.route('/refunds', methods=['POST'])
def create_refund():
    payload = request.json
    required = ['order_id', 'method', 'reason_code']
    if not all(key in payload for key in required):
        return jsonify({"error_code": 400, "message": "Missing fields"}), 400
    orders = get_sheet_data('Orders')
    order = next((row for row in orders if row['order_id'] == payload.get('order_id')), None)
    if not order:
        return jsonify({"error_code": 404, "message": "Order not found"}), 404
    # Eligibility check (e.g., status not 'created')
    if order['status'] == 'created':
        return jsonify({"error_code": 400, "message": "Order not shipped, ineligible for refund"}), 400
    refund_id = f"RF{random.randint(100,999)}"
    amount = random.randint(10, 100)  # Replace with logic (e.g., sum items)
    sla_days = 7
    status = "initiated"
    append_to_sheet('Refunds', {
        'refund_id': refund_id, 'order_id': payload.get('order_id'), 'item_id': payload.get('item_id', ''),
        'amount': amount, 'sla_days': sla_days, 'status': status, 'method': payload['method'], 'reason_code': payload['reason_code']
    })
    return jsonify({"refund_id": refund_id, "amount": amount, "sla_days": sla_days, "status": status})

# Add endpoints for /shipments, /complaints, /returns similarly
# e.g., POST /complaints: Check for duplicates (same order_id, category within 7 days)
@app.route('/complaints', methods=['POST'])
def create_complaint():
    payload = request.json
    required = ['order_id', 'category', 'description']
    if not all(key in payload for key in required):
        return jsonify({"error_code": 400, "message": "Missing fields"}), 400
    complaints = get_sheet_data('Complaints')
    recent_complaints = [c for c in complaints if c['order_id'] == payload['order_id'] and c['category'] == payload['category']]
    if recent_complaints:
        return jsonify({"error_code": 409, "message": "Duplicate complaint detected"}), 409
    ticket_id = f"TK{random.randint(100,999)}"
    priority = 'high' if payload['category'] in ['damaged', 'missing'] else 'standard'
    sla_hours = 4 if priority == 'high' else 24
    append_to_sheet('Complaints', {
        'ticket_id': ticket_id, 'order_id': payload['order_id'], 'category': payload['category'],
        'description': payload['description'], 'evidence_links': payload.get('evidence_links', ''),
        'priority': priority, 'sla_hours': sla_hours
    })
    return jsonify({"ticket_id": ticket_id, "priority": priority, "sla_hours": sla_hours})

# Dynamic Messages endpoint
@app.route('/dynamic-message', methods=['POST'])
def dynamic_message():
    body = request.json
    mobile = body.get('mobile')
    orders = get_sheet_data('Orders')
    user_orders = [row for row in orders if row['phone'] == mobile]
    if not user_orders:
        return jsonify({"additional_info": {"inya_data": {"text": "Hi there!", "user_context": {}}}}), 200
    name = user_orders[0].get('name', 'Customer')
    context = {
        "phone_number": '***-***-' + mobile[-4:],
        "customer_name": name,
        "recent_order_id": user_orders[-1]['order_id'],
        "loyalty_status": "Gold" if len(user_orders) > 1 else "Standard"  # Example rule
    }
    greeting = f"Hi {name}, thanks for calling about your order {context['recent_order_id']}!"
    return jsonify({"additional_info": {"inya_data": {"text": greeting, "user_context": context}}}), 200


@app.route('/disposition', methods=['POST'])
def log_disposition():
    body = request.json
    transcript = body.get('transcript', '')
    # Analyze transcript (simplified; use NLP or regex for real-world)
    call_id = body.get('conversation_id', 'unknown')
    agent_id = 'unknown'  # Extract if available
    user_id = body.get('mobile', 'unknown')[-4:]  # Masked
    scenario = 'mixed'  # Parse transcript for intents (track_order, etc.)
    stage_code = 'RESOLVED' if 'summary' in transcript.lower() else 'INCOMPLETE'
    resolution = 'successfully_resolved' if stage_code == 'RESOLVED' else 'incomplete'
    sentiment = 'positive'  # Simplified
    entities = []  # Parse for order_id, refund_id, etc.
    error_handled = False
    turn_count = transcript.count('\n') // 2  # Rough estimate
    disposition = {
        'call_id': call_id, 'agent_id': agent_id, 'user_id': user_id,
        'scenario_type': scenario, 'stage_code': stage_code, 'resolution': resolution,
        'sentiment': sentiment, 'key_entities_extracted': entities,
        'error_handled': error_handled, 'turn_count': turn_count
    }
    append_to_sheet('Dispositions', disposition)
    return jsonify(disposition), 200



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)