import os
import requests
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify
from urllib.parse import urlencode
from datetime import datetime
from twilio.rest import Client

# Download or create the database
if not os.path.exists('bloodline.db'):
    try:
        url = "https://drive.google.com/uc?export=download&id=1A2B3C4D5E6F7G8H9I0J"  # Replace with your actual FILE_ID
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open('bloodline.db', 'wb') as f:
            f.write(r.content)
    except Exception as e:
        print(f"Failed to download bloodline.db: {str(e)}")
        # Create an empty database as a fallback
        conn = sqlite3.connect('bloodline.db')
        conn.execute('''CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            location TEXT NOT NULL,
            phone TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            location TEXT NOT NULL,
            phone TEXT NOT NULL,
            needed_by TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            payment_method TEXT NOT NULL,
            payment_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
        conn.close()

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app = Flask(__name__)

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect('bloodline.db')
    conn.row_factory = sqlite3.Row
    return conn

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# Donor registration page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            required_fields = ['name', 'blood_group', 'location', 'phone']
            form_data = {}
            for field in required_fields:
                if field not in request.form or not request.form[field]:
                    params = urlencode({'message': f"Missing or empty field: {field}", 'type': 'error'})
                    return redirect(url_for('register') + f'?{params}')
                form_data[field] = request.form[field].strip()

            name = form_data['name']
            blood_group = form_data['blood_group'].upper()
            location = form_data['location'].upper()
            phone = form_data['phone']

            # Validate phone number (basic check for 10 digits)
            if not (phone.isdigit() and len(phone) == 10):
                params = urlencode({'message': 'Phone number must be 10 digits.', 'type': 'error'})
                return redirect(url_for('register') + f'?{params}')

            # Validate blood group
            valid_blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
            if blood_group not in valid_blood_groups:
                params = urlencode({'message': 'Invalid blood group.', 'type': 'error'})
                return redirect(url_for('register') + f'?{params}')

            conn = get_db_connection()
            conn.execute('INSERT INTO donors (name, blood_group, location, phone) VALUES (?, ?, ?, ?)',
                         (name, blood_group, location, phone))
            conn.commit()
            conn.close()

            params = urlencode({'message': 'Donor registered successfully!', 'type': 'success'})
            return redirect(url_for('index') + f'?{params}')
        except Exception as e:
            params = urlencode({'message': f"Error: {str(e)}", 'type': 'error'})
            return redirect(url_for('register') + f'?{params}')
    return render_template('register.html')

# Donor search page
@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        try:
            required_fields = ['blood_group', 'location']
            form_data = {}
            for field in required_fields:
                if field not in request.form or not request.form[field]:
                    params = urlencode({'message': f"Missing or empty field: {field}", 'type': 'error'})
                    return redirect(url_for('search') + f'?{params}')
                form_data[field] = request.form[field].strip().upper()

            blood_group = form_data['blood_group'].replace('0+', 'O+').replace('0-', 'O-')
            blood_group_map = {
                'A POSITIVE': 'A+', 'A NEGATIVE': 'A-',
                'B POSITIVE': 'B+', 'B NEGATIVE': 'B-',
                'AB POSITIVE': 'AB+', 'AB NEGATIVE': 'AB-',
                'O POSITIVE': 'O+', 'O NEGATIVE': 'O-'
            }
            blood_group = blood_group_map.get(blood_group, blood_group)

            location = form_data['location']

            conn = get_db_connection()
            donors = conn.execute('SELECT * FROM donors WHERE blood_group = ? AND location = ?',
                                  (blood_group, location)).fetchall()
            conn.close()

            if not donors:
                return render_template('search_results.html', donors=[], message='No donors found for the given criteria.', message_type='error')

            return render_template('search_results.html', donors=donors, message=f"Found {len(donors)} donor(s)!", message_type='success')
        except Exception as e:
            params = urlencode({'message': f"Error: {str(e)}", 'type': 'error'})
            return redirect(url_for('search') + f'?{params}')
    return render_template('search.html')

# Blood request page with SMS notification
@app.route('/request', methods=['GET', 'POST'])
def request_blood():
    if request.method == 'POST':
        try:
            required_fields = ['name', 'blood_group', 'location', 'phone', 'needed_by']
            form_data = {}
            for field in required_fields:
                if field not in request.form or not request.form[field]:
                    params = urlencode({'message': f"Missing or empty field: {field}", 'type': 'error'})
                    return redirect(url_for('request_blood') + f'?{params}')
                form_data[field] = request.form[field].strip()

            name = form_data['name']
            blood_group = form_data['blood_group'].upper()
            location = form_data['location'].upper()
            phone = form_data['phone']
            needed_by = form_data['needed_by']

            # Validate phone number
            if not (phone.isdigit() and len(phone) == 10):
                params = urlencode({'message': 'Phone number must be 10 digits.', 'type': 'error'})
                return redirect(url_for('request_blood') + f'?{params}')

            # Validate blood group
            valid_blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
            if blood_group not in valid_blood_groups:
                params = urlencode({'message': 'Invalid blood group.', 'type': 'error'})
                return redirect(url_for('request_blood') + f'?{params}')

            # Validate needed_by date (basic check for format YYYY-MM-DD)
            try:
                datetime.strptime(needed_by, '%Y-%m-%d')
            except ValueError:
                params = urlencode({'message': 'Invalid date format for "Needed By". Use YYYY-MM-DD.', 'type': 'error'})
                return redirect(url_for('request_blood') + f'?{params}')

            # Save request to database
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO requests (name, blood_group, location, phone, needed_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, blood_group, location, phone, needed_by))

            # Notify matching donors via SMS
            donors = conn.execute('''
                SELECT phone FROM donors
                WHERE blood_group = ? AND location = ?
            ''', (blood_group, location)).fetchall()

            for donor in donors:
                donor_phone = f"+91{donor['phone']}"
                try:
                    message = client.messages.create(
                        body=f"Urgent request: {name} needs {blood_group} blood in {location}. Contact: {phone}. Required by: {needed_by}.",
                        from_=TWILIO_PHONE_NUMBER,
                        to=donor_phone
                    )
                    print(f"SMS sent to {donor_phone}: {message.sid}")
                except Exception as e:
                    print(f"Failed to send SMS to {donor_phone}: {str(e)}")
                    # Continue with the next donor instead of failing

            conn.commit()
            conn.close()

            params = urlencode({'message': 'Blood request submitted successfully!', 'type': 'success'})
            return redirect(url_for('index') + f'?{params}')
        except Exception as e:
            params = urlencode({'message': f"Error: {str(e)}", 'type': 'error'})
            return redirect(url_for('request_blood') + f'?{params}')
    return render_template('request.html')

# Donations page with multiple payment methods
@app.route('/donate', methods=['GET', 'POST'])
def donate():
    conn = sqlite3.connect('bloodline.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM donors')
    donors = cursor.fetchall()
    print("Fetched donors:", donors)
    conn.close()

    if request.method == 'POST':
        try:
            donor_name = request.form.get('donor_name')
            amount = request.form.get('amount')
            payment_method = request.form.get('payment_method')
            if not donor_name or not amount or not payment_method:
                return redirect(url_for('donate', message='Missing or empty field: donor_name, amount, or payment_method', type='error'))
            order_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            callback_url = url_for('payment_callback', _external=True)
            return redirect(url_for('payment_simulation', name=donor_name, amount=amount, order_id=order_id, callback_url=callback_url, payment_method=payment_method))
        except Exception as e:
            print(f"Error in POST /donate: {str(e)}")
            return redirect(url_for('donate', message=f'Error processing donation: {str(e)}', type='error'))
    else:
        message = request.args.get('message')
        msg_type = request.args.get('type')
        return render_template('donate.html', donors=donors, message=message, type=msg_type)

# Payment simulation route
@app.route('/payment_simulation')
def payment_simulation():
    name = request.args.get('name')
    amount = request.args.get('amount')
    order_id = request.args.get('order_id')
    callback_url = request.args.get('callback_url')
    payment_method = request.args.get('payment_method')
    print(f"Payment method in /payment_simulation: '{payment_method}'")

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Simulation - BloodLine</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
            h1 { color: #d32f2f; text-align: center; }
            p { font-size: 1.1em; }
            form { margin-top: 20px; }
            label { display: block; margin: 10px 0 5px; font-weight: bold; }
            input[type="text"] { width: 100%; padding: 8px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; }
            button { background-color: #d32f2f; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #b71c1c; }
        </style>
    </head>
    <body>
        <h1>Payment Simulation</h1>
        <p>Donor: {name}</p>
        <p>Amount: ₹{amount}</p>
        <p>Order ID: {order_id}</p>
        <p>Payment Method: {payment_method.upper()}</p>
    """

    if payment_method == 'credit_card':
        html += ('<h3>Enter Credit Card Details</h3><form action="{}" method="POST">'
                 '<input type="hidden" name="name" value="{}">'
                 '<input type="hidden" name="amount" value="{}">'
                 '<input type="hidden" name="order_id" value="{}">'
                 '<input type="hidden" name="payment_method" value="{}">'
                 '<label for="card_number">Card Number:</label>'
                 '<input type="text" id="card_number" name="card_number" placeholder="1234-5678-9012-3456" required>'
                 '<label for="expiry">Expiry Date (MM/YY):</label>'
                 '<input type="text" id="expiry" name="expiry" placeholder="MM/YY" required>'
                 '<label for="cvv">CVV:</label>'
                 '<input type="text" id="cvv" name="cvv" placeholder="123" required>'
                 '<button type="submit">Submit Payment</button></form>').format(callback_url, name, amount, order_id, payment_method)
    elif payment_method == 'bank_transfer':
        html += ('<h3>Enter Bank Account Details</h3><form action="{}" method="POST">'
                 '<input type="hidden" name="name" value="{}">'
                 '<input type="hidden" name="amount" value="{}">'
                 '<input type="hidden" name="order_id" value="{}">'
                 '<input type="hidden" name="payment_method" value="{}">'
                 '<label for="account_number">Account Number:</label>'
                 '<input type="text" id="account_number" name="account_number" placeholder="1234567890" required>'
                 '<label for="ifsc">IFSC Code:</label>'
                 '<input type="text" id="ifsc" name="ifsc" placeholder="ABCD0001234" required>'
                 '<button type="submit">Submit Payment</button></form>').format(callback_url, name, amount, order_id, payment_method)
    else:  # e.g., 'gpay'
        html += ('<form action="{}" method="POST">'
                 '<input type="hidden" name="name" value="{}">'
                 '<input type="hidden" name="amount" value="{}">'
                 '<input type="hidden" name="order_id" value="{}">'
                 '<input type="hidden" name="payment_method" value="{}">'
                 '<button type="submit">Simulate Success</button></form>').format(callback_url, name, amount, order_id, payment_method)

    html += """
    </body>
    </html>
    """
    return html

@app.route('/payment_callback', methods=['POST'])
def payment_callback():
    try:
        name = request.form.get('name')
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method')
        print(f"Form data in /payment_callback: {request.form}")

        if not name or not amount or not payment_method:
            raise ValueError("Missing required fields: name, amount, or payment_method")

        if payment_method == 'credit_card':
            card_number = request.form.get('card_number')
            expiry = request.form.get('expiry')
            cvv = request.form.get('cvv')
            if not card_number or not expiry or not cvv:
                raise ValueError("Missing credit card details")
            payment_details = f"Card ending in {card_number[-4:]} (Expiry: {expiry})"
        elif payment_method == 'bank_transfer':
            account_number = request.form.get('account_number')
            ifsc = request.form.get('ifsc')
            if not account_number or not ifsc:
                raise ValueError("Missing bank account details")
            payment_details = f"Account ending in {account_number[-4:]} (IFSC: {ifsc})"
        else:
            payment_details = payment_method.upper()

        conn = sqlite3.connect('bloodline.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO donations (donor_name, amount, payment_method, payment_details, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
                       (name, amount, payment_method, payment_details))
        conn.commit()
        conn.close()

        return redirect(url_for('donate', message=f'Thank you, {name}, for your {payment_method.upper()} donation of ₹{amount}!', type='success'))
    except Exception as e:
        return redirect(url_for('donate', message=f'Error: {str(e)}', type='error'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
