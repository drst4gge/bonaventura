from flask import Flask, request, render_template, redirect, url_for
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import pymysql
import http.client
import json
from flask import session, redirect, url_for, flash
from functools import wraps
from dotenv import load_dotenv
import os
import stripe

application = Flask(__name__)
load_dotenv()

stripe.api_key = 'your_stripe_secret_key'
application.secret_key = os.environ.get('SECRET_KEY')

def requires_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] not in roles:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return wrapper

# Database Helper Functions
def get_db_connection():
    return pymysql.connect(
        host="bonaventura-mysql.cponyf6gvfgg.us-east-1.rds.amazonaws.com",
        user="admin",
        password="Mylove707",
        db="properties",
        port=3306
    )

def insert_address(address, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, photo_url):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            insert_sql = """
            INSERT INTO all_properties (addresses, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, photo_url) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (address, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, photo_url))
        conn.commit()
    finally:
        conn.close()

def get_all_properties():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:  # Ensure DictCursor is used
            cursor.execute("SELECT id, addresses, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, photo_url FROM all_properties")
            return cursor.fetchall()
    finally:
        conn.close()


def get_property_by_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:  # Use DictCursor here
            cursor.execute("SELECT * FROM all_properties WHERE id = %s", (property_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def get_unique_counties():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:  # Use DictCursor here
            cursor.execute("SELECT DISTINCT county FROM all_properties WHERE county IS NOT NULL")
            return [row['county'] for row in cursor.fetchall()]
    finally:
        conn.close()


def update_property(property_id, address, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, county, taxAssessedYear):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = """
            UPDATE all_properties 
            SET addresses = %s, zpid = %s, bedrooms = %s, bathrooms = %s, livingArea = %s, lotSize = %s, price = %s, taxAssessedValue = %s, county = %s, taxAssessedYear = %s 
            WHERE id = %s
            """
            cursor.execute(update_sql, (address, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, property_id))
        conn.commit()
    finally:
        conn.close()

def delete_property(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            delete_sql = "DELETE FROM all_properties WHERE id = %s"
            cursor.execute(delete_sql, (property_id,))
        conn.commit()
    finally:
        conn.close()

def get_zpid_from_address(address):
    conn = http.client.HTTPSConnection("zillow56.p.rapidapi.com")
    headers = {
        'X-RapidAPI-Key': "d0464de0f3msh4f7ea52273787c1p12b945jsn3e3da4819696",
        'X-RapidAPI-Host': "zillow56.p.rapidapi.com"
    }

    formatted_address = address.replace(" ", "%20")
    conn.request("GET", f"/search_address?address={formatted_address}", headers=headers)

    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))

    zpid = response_json.get("zpid", None)
    return zpid

def get_property_details(zpid):
    conn = http.client.HTTPSConnection("zillow56.p.rapidapi.com")
    headers = {
        'X-RapidAPI-Key': "d0464de0f3msh4f7ea52273787c1p12b945jsn3e3da4819696",
        'X-RapidAPI-Host': "zillow56.p.rapidapi.com"
    }

    conn.request("GET", f"/property?zpid={zpid}", headers=headers)

    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))

    # Extract the desired details from the response
    # This depends on the structure of the response and what information you need
    bedrooms = response_json.get('bedrooms', 'N/A')
    bathrooms = response_json.get('bathrooms', 'N/A')
    livingArea = response_json.get('livingArea', 'N/A')
    lotSize = response_json.get('lotSize', 'N/A')
    price = response_json.get('price', 'N/A')
    taxAssessedValue = response_json.get('taxAssessedValue', 'N/A')
    taxAssessedYear = response_json.get('taxAssessedYear', 'N/A')
    county = response_json.get('county', 'N/A')

    return {
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'livingArea': livingArea,
        'lotSize': lotSize,
        'price': price,
        'taxAssessedValue': taxAssessedValue,
        'taxAssessedYear': taxAssessedYear,
        'county': county
    }

@application.route('/')
def home():
    return render_template('index.html')

@application.route('/pricing')
def pricing():
    return render_template('pricing.html')

@application.route('/services')
def services():
    return render_template('services.html')

@application.route('/properties')
def properties_page():
    properties = get_all_properties()
    users = get_all_users()
    # Convert 'id' to integer if necessary
    for property in properties:
        property['id'] = int(property['id'])
    return render_template('properties.html', properties=properties)

@application.route('/subscriber')
@requires_roles(0)
def subscriber():
    properties = get_all_properties()
    counties = get_unique_counties()
    # Convert 'id' to integer if necessary
    for property in properties:
        property['id'] = int(property['id'])
    
    return render_template('subscriber.html', properties=properties, counties=counties)

@application.route('/agent')
@requires_roles(1)
def agent():
    properties = get_all_properties()
    users = get_all_users()
    # Convert 'id' to integer if necessary
    for property in properties:
        property['id'] = int(property['id'])
    return render_template('agent.html', properties=properties)

@application.route('/admin')
@requires_roles(2)
def admin():
    properties = get_all_properties()
    users = get_all_users()
    # Convert 'id' to integer if necessary
    for property in properties:
        property['id'] = int(property['id'])
    return render_template('admin.html', properties=properties, users=users)

@application.route('/delete_user/<int:user_id>', methods=['GET'])
def delete_user(user_id):
    # Delete user from the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()

    flash('User deleted successfully!')
    return redirect(url_for('admin'))

@application.route('/edit_user/<int:user_id>', methods=['GET'])
def edit_user(user_id):
    # Fetch user details from the database
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
    finally:
        conn.close()

    if user:
        return render_template('edit_user.html', user=user)
    else:
        flash('User not found.')
        return redirect(url_for('admin'))

@application.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    # Extract form data
    username = request.form['username']
    email = request.form['email']
    phone = request.form['phone']
    role = request.form['role']

    # Update user details in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE users SET username = %s, email = %s, phone = %s, role = %s WHERE id = %s"
            cursor.execute(sql, (username, email, phone, role, user_id))
        conn.commit()
    finally:
        conn.close()

    flash('User updated successfully!')
    return redirect(url_for('admin'))

def get_all_users():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users")
            return cursor.fetchall()
    finally:
        conn.close()

@application.route('/property/<int:id>')
def property_details(id):
    property = get_property_by_id(id)

    if property:
        return render_template('property_details.html', property=property)
    else:
        return 'Property not found', 404

@application.route('/login', methods=['GET'])
def login_form():
    return render_template('login.html')

def get_hashed_password(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        return result[0]  # Assuming 'password' is the first field
    else:
        return None
    
@application.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']  # Store user ID in session
        session['user_email'] = user['email']  # Store user email in session
        session['user_phone'] = user['phone']  # Store user phone in session
        session['user_role'] = user['role']
        if user['role'] == 0:
            return redirect(url_for('subscriber'))
        elif user['role'] == 1:
            return redirect(url_for('agent'))
        elif user['role'] == 2:
            return redirect(url_for('admin'))
        else:
            return 'Invalid role', 401
    else:
        return 'Invalid credentials', 401

    
@application.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'GET':
        return render_template('create_user.html')
    else:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form['phone']
        role = request.form['role']  # Ensure this is properly validated and secured

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, email, phone, role) VALUES (%s, %s,%s, %s, %s)",
                       (username, hashed_password, email, phone, role))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('login_form'))
    
@application.route('/logout')
def logout():
    session.pop('user_role', None)  # Remove the user role from session
    # Redirect to login page or home page

@application.route('/add_address', methods=['GET'])
def add_address():
    return render_template('add_address.html')

@application.route('/add_user', methods=['GET'])
def add_user():
    return render_template('add_user.html')

@application.route('/submit_address', methods=['POST'])
def submit_address():
    address = request.form['address']
    zpid = get_zpid_from_address(address)
    photo_url = None

    if zpid:
        details = get_property_details(zpid)
        photo_url = get_photos(zpid)
        insert_address(
            address, 
            zpid, 
            details.get('bedrooms', None),
            details.get('bathrooms', None),
            details.get('livingArea', None),
            details.get('lotSize', None),
            details.get('price', None),
            details.get('taxAssessedValue', None),
            details.get('taxAssessedYear', None),
            details.get('county', None),
            photo_url
        )

    else:
        # Handle the case where no details are available
        insert_address(address, None, None, None, None, None, None, None, None, None, None)

    return redirect(url_for('admin'))

@application.route('/submit_user', methods=['POST'])
def submit_user():
    # Extract form data
    username = request.form['username']
    password = request.form['password']
    email = request.form['email']
    phone = request.form['phone']
    role = request.form['role']

    # Hash the password
    hashed_password = generate_password_hash(password)

    # Connect to database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Insert new user
            sql = "INSERT INTO users (username, password, email, phone, role) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (username, hashed_password, email, phone, role))
        conn.commit()
    finally:
        conn.close()

    flash('User created successfully!')
    return redirect(url_for('admin'))



@application.route('/edit/<int:id>', methods=['GET'])
def edit_address(id):
    property = get_property_by_id(id)
    if property:
        return render_template('edit_address.html', property=property)
    return 'Property not found', 404

@application.route('/update_address', methods=['POST'])
def update_address():
    property_id = request.form['id']
    address = request.form['address']
    # Assuming you have form fields for these values
    zpid = request.form['zpid']
    bedrooms = request.form['bedrooms']
    bathrooms = request.form['bathrooms']
    livingArea = request.form['livingArea']
    lotSize = request.form['lotSize']
    price = request.form['price']
    taxAssessedValue = request.form['taxAssessedValue']
    taxAssessedYear = request.form['taxAssessedYear']
    county = request.form['county']

    update_property(property_id, address, zpid, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county)
    return redirect(url_for('home'))

@application.route('/delete/<int:id>', methods=['GET'])
def delete_address(id):
    delete_property(id)
    return redirect(url_for('admin'))


def get_photos(zpid):
    conn = http.client.HTTPSConnection("zillow56.p.rapidapi.com")
    headers = {
        'X-RapidAPI-Key': "d0464de0f3msh4f7ea52273787c1p12b945jsn3e3da4819696",
        'X-RapidAPI-Host': "zillow56.p.rapidapi.com"
    }

    conn.request("GET", f"/photos?zpid={zpid}", headers=headers)
    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))

    # Check if 'photos' key exists and has at least one photo
    if 'photos' in response_json and response_json['photos']:
        # Access the first photo's 'mixedSources'
        mixed_sources = response_json['photos'][0].get('mixedSources', {})
        # Check if 'jpeg' key exists and has at least one JPEG source
        if 'jpeg' in mixed_sources and mixed_sources['jpeg']:
            # Access the 'url' of the first JPEG source
            first_photo_url = mixed_sources['jpeg'][0].get('url', None)
            return first_photo_url

    return None  # Return None if no photo URL is found

@application.route('/bid/<int:id>', methods=['GET'])
def bid(id):
    property = get_property_by_id(id)
    if property:
        user_details = {
            'username': session.get('username', ''),
            'email': session.get('user_email', ''),
            'phone': session.get('user_phone', '')
        }
        return render_template('bid.html', property_id=id, user=user_details)
    else:
        return 'Property not found', 404

@application.route('/submit_bid/<int:id>', methods=['POST'])
def submit_bid(id):
    # Here you would handle the bid submission
    # For example, save the bid to the database

    name = request.form['name']
    email = request.form['email']
    phone = request.form['phone']
    bid_amount = request.form['bid']

    # Save the bid information to the database or process it as needed

    # Redirect to a confirmation page or back to the property details
    return redirect(url_for('property_details', id=id))

@application.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Premium Account',
                },
                'unit_amount': 1000,  # price in cents
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://yourdomain.com/success',
        cancel_url='https://yourdomain.com/cancel',
    )
    return redirect(session.url, code=303)

# Webhook endpoint for Stripe
@application.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, 'your_stripe_webhook_secret'
        )

        # Handle the checkout.session.completed event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']

            # Perform actions after successful payment (e.g., activate user account)
            # ...

    except ValueError as e:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return 'Invalid signature', 400

    return 'Success', 200



if __name__ == "__main__":
    application.run()

