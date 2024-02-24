from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import pymysql
import http.client
import json
from flask import session, redirect, url_for, flash
from functools import wraps
from dotenv import load_dotenv
import os
import stripe
import re
from PyPDF2 import PdfReader
from datetime import datetime, timedelta
import calendar
from stripe.error import InvalidRequestError

application = Flask(__name__)
load_dotenv()

stripe.api_key = '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'
application.secret_key = os.environ.get('SECRET_KEY')

UPLOAD_FOLDER = 'static/pdfs' 
IMAGES_FOLDER = 'static/images' 
ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_EXTENSIONS_PHOTO = {'png', 'jpg', 'jpeg'}

application.config['UPLOAD_FOLDER'] = 'static/pdfs'
application.config['IMAGES_FOLDER'] = 'static/images'

def format_currency(value):
    # Format the number as a currency, with commas for thousands and two decimal places
    # Assuming USD for currency; adjust the symbol as needed
    return "${:,.2f}".format(value)

# Register the filter with your Jinja environment
application.jinja_env.filters['format_currency'] = format_currency

def split_address(address):
    return address.split(' - ')[0]

# Register the filter with Jinja
application.jinja_env.filters['split_address'] = split_address


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

def insert_address(address, zpid, bedrooms, bathrooms, livingArea, lotSize, county, photo_url, date_of_sale, time_of_sale, price):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            insert_sql = """
            INSERT INTO all_properties 
            (addresses, zpid, bedrooms, bathrooms, livingArea, lotSize, county, photo_url, dateOfSale, timeOfSale, price) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (address, zpid, bedrooms, bathrooms, livingArea, lotSize, county, photo_url, date_of_sale, time_of_sale, price))
        conn.commit()
    finally:
        conn.close()

def get_all_properties():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Include price in the SELECT query
            cursor.execute("SELECT id, addresses, bedrooms, bathrooms, livingArea, lotSize, county, dateOfSale, timeOfSale, photo_url, price FROM all_properties")
            return cursor.fetchall()
    finally:
        conn.close()

def get_property_by_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM all_properties WHERE id = %s", (property_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def get_photos_by_property_id(property_id):
    conn = get_db_connection()
    photos = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            query = "SELECT id, photo_url FROM property_photos WHERE property_id = %s"
            cursor.execute(query, (property_id,))
            photos = cursor.fetchall()  # Fetch all photo entries matching the property_id
    except Exception as e:
        print(f"Error fetching photos for property_id {property_id}: {e}")
    finally:
        conn.close()
    return photos

def get_unique_counties():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:  # Use DictCursor here
            cursor.execute("SELECT DISTINCT county FROM all_properties WHERE county IS NOT NULL")
            return [row['county'] for row in cursor.fetchall()]
    finally:
        conn.close()

def update_property(property_id, dateOfSale, timeOfSale, price):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = """
            UPDATE all_properties 
            SET dateOfSale = %s, timeOfSale = %s, price = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (dateOfSale, timeOfSale, price, property_id))
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
    # Clean the address by removing newline characters and other potential control characters
    cleaned_address = re.sub(r'\s+', ' ', address.strip())
    formatted_address = cleaned_address.replace(" ", "%20")
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

    # Define a helper function to handle None values
    def get_value_or_placeholder(key, placeholder='--'):
        value = response_json.get(key)
        return value if value is not None else placeholder

    bedrooms = get_value_or_placeholder('bedrooms')
    bathrooms = get_value_or_placeholder('bathrooms')
    livingArea = get_value_or_placeholder('livingArea')
    lotSize = get_value_or_placeholder('lotSize')
    county = get_value_or_placeholder('county')

    return {
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'livingArea': livingArea,
        'lotSize': lotSize,
        'county': county,
    }

@application.route('/')
def home():
    today = datetime.today()
    current_date = today.strftime('%Y-%m-%d')
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    selected_county = request.args.get('county', type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime('%B')

    properties = get_all_properties()  # Fetch all properties
    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    # Filter properties by selected county
    if selected_county:
        properties = [prop for prop in properties if prop.get('county') == selected_county]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop('year', None)
    calendar_data.pop('month', None)

    return render_template('index.html', current_month=current_month, year=year, month=month, current_date=current_date, selected_county=selected_county, counties=counties, **calendar_data)
    

@application.route('/pricing')
def pricing():
    return render_template('pricing.html')

@application.route('/subscriber_agreement')
def subscriber_agreement():
    return render_template('subscriber_agreement.html')

@application.route('/bid_agreement')
def bid_agreement():
    return render_template('bid_agreement.html')

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
    user_id = session.get('user_id')
    if not user_id:
        # Handle the case where there is no user logged in
        flash('You need to be logged in to view this page.')
        return redirect(url_for('login_form'))
    today = datetime.today()
    current_date = today.strftime('%Y-%m-%d')
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    selected_county = request.args.get('county', type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime('%B')
    properties = get_all_properties()  # Fetch all properties
    counties = get_unique_counties()
    # Fetch all properties with their latest photo URLs
    
    
    if selected_county:
        properties = [prop for prop in properties if prop.get('county') == selected_county]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop('year', None)
    calendar_data.pop('month', None)

    counties = get_unique_counties()  # Fetch unique counties for filter dropdown
    user = get_user_by_id(user_id)
    return render_template('subscriber.html', user=user, current_month=current_month, year=year, month=month, current_date=current_date, selected_county=selected_county, counties=counties, **calendar_data)
    
    
    

@application.route('/agent')
@requires_roles(1)
def agent():
    county_filter = request.args.get('county')
    properties = get_all_properties()

    # Filter properties by date and county if selected
    filtered_properties = []
    for prop in properties:
        prop_date = prop['dateOfSale']
        if isinstance(prop_date, str):
            prop_date = datetime.strptime(prop_date, '%Y-%m-%d').date()

        if prop_date >= datetime.now().date():
            if not county_filter or (county_filter and prop.get('county') == county_filter):
                filtered_properties.append(prop)

    # Sort the filtered properties by 'dateOfSale'
    filtered_properties.sort(key=lambda x: x['dateOfSale'])

    # Group properties by 'dateOfSale' and include the day of the week
    properties_by_date_with_day = {}
    for prop in filtered_properties:
        prop_date = prop['dateOfSale']
        if isinstance(prop_date, str):
            prop_date = datetime.strptime(prop_date, '%Y-%m-%d').date()

        day_name = prop_date.strftime('%A')  # Gets the day name (e.g., 'Monday')
        formatted_date = f"{day_name}, {prop_date.strftime('%Y-%m-%d')}"  # Format: 'Day, YYYY-MM-DD'
        properties_by_date_with_day.setdefault(formatted_date, []).append(prop)

    # Get unique counties for the filter dropdown
    counties = get_unique_counties()
    
    return render_template('agent.html', properties_by_date=properties_by_date_with_day, counties=counties, selected_county=county_filter)

def generate_calendar(year, month, properties):
    if month > 12:
        year += 1
        month = 1
    elif month < 1:
        year -= 1
        month = 12

    first_day_of_month = datetime(year, month, 1)
    last_day_of_month = datetime(year, month, calendar.monthrange(year, month)[1])

    first_weekday = first_day_of_month.weekday()
    days_in_month = (last_day_of_month - first_day_of_month).days + 1

    # Create a dictionary to hold property data for each day
    properties_by_date = {day: [] for day in range(1, days_in_month + 1)}

    # Populate the dictionary with property data
    for prop in properties:
        prop_date = prop['dateOfSale']
        if isinstance(prop_date, str):
            prop_date = datetime.strptime(prop_date, '%Y-%m-%d').date()
        if prop_date.year == year and prop_date.month == month:
            properties_by_date[prop_date.day].append(prop)

    return {
        "year": year,
        "month": month,
        "first_weekday": first_weekday,
        "days_in_month": days_in_month,
        "properties_by_date": properties_by_date
    }

@application.route('/admin')
@requires_roles(2)
def admin():
    today = datetime.today()
    current_date = today.strftime('%Y-%m-%d')
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    selected_county = request.args.get('county', type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime('%B')
    properties = get_all_properties()  # Fetch all properties
    counties = get_unique_counties()
    # Fetch all properties with their latest photo URLs
    
    
    if selected_county:
        properties = [prop for prop in properties if prop.get('county') == selected_county]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop('year', None)
    calendar_data.pop('month', None)

    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    return render_template('admin.html', current_month=current_month, year=year, month=month, current_date=current_date, selected_county=selected_county, counties=counties, **calendar_data)

@application.route('/admin_usercontrol', methods=['GET'])
@requires_roles(2)
def admin_usercontrol():
    users = get_all_users()
    county_filter = request.args.get('county')
    counties = get_unique_counties()
    return render_template('admin_usercontrol.html', users=users, counties=counties, selected_county=county_filter)

@application.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login_form'))

    user_id = session['user_id']
    user = get_user_by_id(user_id)
    
    if request.method == 'GET':
        return render_template('edit_profile.html', user=user)
    else:
        # Get data from form
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        # Update user information in the database
        update_user(user_id, username, email, phone)
        return redirect(url_for('admin'))


from stripe.error import StripeError

@application.route('/delete_user/<int:user_id>', methods=['GET'])
def delete_user(user_id):
    conn = get_db_connection()
    try:
        # Retrieve the user to get the Stripe customer ID
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

        # Check if the user has a Stripe customer ID
        if user and 'stripe_customer_id' in user and user['stripe_customer_id']:
            try:
                # Delete the Stripe customer
                stripe.Customer.delete(user['stripe_customer_id'])
            except StripeError as e:
                # Handle errors from Stripe
                flash(f"Stripe error: {e.user_message}")
                return redirect(url_for('admin_usercontrol'))

        # Now delete the user from the database
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        flash('User and Stripe customer deleted successfully!')
    except Exception as e:
        flash(f"An error occurred: {e}")
    finally:
        conn.close()

    return redirect(url_for('admin_usercontrol'))

@application.route('/delete_subscription/<int:user_id>', methods=['GET'])
def delete_subscription(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        flash('Unauthorized access.')
        return redirect(url_for('home'))

    try:
        user = get_user_by_id(user_id)

        # Delete the subscription from Stripe
        delete_stripe_subscription(user['stripe_customer_id'])

        # Delete the user from the database
        

        flash('Subscription cancelled successfully.')
        return redirect(url_for('home'))
    except Exception as e:
        flash(f'Error: {e}')
        return redirect(url_for('subscriber'))

def delete_stripe_subscription(stripe_subscription_id):
    try:
        stripe.Subscription.delete(stripe_subscription_id)
    except stripe.error.StripeError as e:
        # Handle Stripe errors
        print(f"Stripe Error: {e}")


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
        return redirect(url_for('home'))

@application.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    # Extract form data
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    username = request.form['username']
    email = request.form['email']
    phone = request.form['phone']

    # Update user details in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = "UPDATE users SET first_name = %s, last_name = %s, username = %s, email = %s, phone = %s WHERE id = %s"
            cursor.execute(update_sql, (first_name, last_name, username, email, phone, user_id))
        conn.commit()
    finally:
        conn.close()

    flash('User updated successfully!')

    # Redirect based on user role

    return redirect(url_for('login_form'))
    




def get_all_users():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users")
            return cursor.fetchall()
    finally:
        conn.close()

def get_user_by_id(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        conn.close()

@application.route('/property/<int:id>')
def property_details(id):
    property = get_property_by_id(id)
    photos = get_photos_by_property_id(id)

    if property:
        return render_template('property_details.html', property=property, photos=photos)
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
        # Set common user info in session
        session['user_id'] = user['id'] 
        session['user_email'] = user['email'] 
        session['first_name'] = user['first_name'] 
        session['last_name'] = user['last_name'] 
        session['user_phone'] = user['phone'] 
        session['user_role'] = user['role']
        session['user_username'] = user['username']
        session['stripe_customer_id'] = user['stripe_customer_id']
        
        if user['role'] in [1, 2]:  # Assuming 1 is for agents and 2 is for admins
            return redirect(url_for('admin')) if user['role'] == 2 else redirect(url_for('agent'))

        # For subscribers, check active subscription
        has_active_subscription, subscription_level = check_active_subscription(user)
        if has_active_subscription:
            session['subscription_level'] = subscription_level
            return redirect(url_for('subscriber'))
        else:
            flash('No active subscription found. Please subscribe to continue.')
            return redirect(url_for('pricing'))
    else:
        flash('Invalid username or password.')
        return redirect(url_for('login_form'))

def check_active_subscription(user):
    stripe_customer_id = user.get('stripe_customer_id')
    print(f"Checking active subscription for Stripe customer ID: {stripe_customer_id}")

    # Reverse mapping from price ID to subscription level
    price_to_subscription_level = {
        'price_1OYcdNFNut4X8qSwqIIX5Yz5': 'test',
        'price_1OYc4qFNut4X8qSwK07XJ8M2': 'standard',
        'price_1Of8KoFNut4X8qSwksIcg5js': 'gold',
        'price_1Of8LFFNut4X8qSw1Kvnlavx': 'platinum',
    }

    if not stripe_customer_id:
        print("No Stripe customer ID found for user.")
        application.logger.error("Stripe customer ID not found for user.")
        return False, 'none'

    try:
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            status='active',
            limit=1
        )
        if subscriptions.data:
            # Fetch the first active subscription
            subscription = subscriptions.data[0]
            # Assuming each subscription has at least one item and we're interested in the first one
            for item in subscription['items']:
                price_id = item['price']['id']
                subscription_level = price_to_subscription_level.get(price_id, 'unknown')
                print(f"Found active subscription with Price ID: {price_id}, interpreted as {subscription_level} level.")
                return True, subscription_level

        print("No active subscriptions found for the user.")
        return False, 'none'
    except Exception as e:
        print(f"Error during subscription check: {e}")
        application.logger.error(f"Error checking active subscription: {e}")
        return False, 'none'


@application.route('/register', methods=['GET'])
def show_registration_form():
    return render_template('create_user.html')

from stripe.error import StripeError

@application.route('/register_user', methods=['POST'])
def register_user():
    try:
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form['phone']
        role = request.form['role']
        subscription_level = request.form['subscriptionLevel']

        if username_exists(username):
            return redirect(url_for('show_registration_form'))
        
        if not re.match("^[A-Za-z0-9]+$", username):
            flash("Invalid username. Only characters and integers are allowed.")
            return redirect(url_for('show_registration_form'))
        
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email format.")
            return redirect(url_for('show_registration_form'))

        if not re.match(r"\d{10,12}", phone):
            flash("Phone number must be 10, 11, or 12 digits.")
            return redirect(url_for('show_registration_form'))
        

        # Create user in the database with Stripe customer ID
        user_id = create_user_in_db(first_name, last_name, username, password, email, phone, role, stripe_customer_id=None)


        return redirect(url_for('create_checkout_session', user_id=user_id, subscription_level=subscription_level), code=307)
    except StripeError as e:
        # Handle errors from Stripe
        flash(f"Stripe error: {e.user_message}")
        return redirect(url_for('show_registration_form'))
    except Exception as e:
        # Handle other errors
        flash(f"An error occurred: {e}")
        return redirect(url_for('show_registration_form'))

def create_user_in_db(first_name, last_name, username, password, email, phone, role, stripe_customer_id=None):
    # Your existing database logic to create a user, now including stripe_customer_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (first_name, last_name, username, password, email, phone, role, stripe_customer_id) VALUES (%s, %s, %s, %s,%s, %s, %s, %s)",
                   (first_name, last_name, username, generate_password_hash(password), email, phone, role, stripe_customer_id))
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return user_id

def username_exists(username):
    """Check if a username already exists in the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return True  # Username exists
            else:
                return False  # Username does not exist
    finally:
        conn.close()

@application.route('/check_username', methods=['POST'])
def check_username():
    username = request.form['username']
    if username_exists(username):
        return jsonify({'exists': True})
    return jsonify({'exists': False})


    
@application.route('/logout')
def logout():
    session.pop('user_role', None)  # Remove the user role from session
    return redirect(url_for('home'))

@application.route('/add_address', methods=['GET'])
def add_address():
    return render_template('add_address.html')

@application.route('/add_user', methods=['GET'])
def add_user():
    return render_template('add_user.html')



@application.route('/submit_address', methods=['POST'])
def submit_address():
    address = request.form['address']
    dateOfSale = None
    timeOfSale = None
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
            details.get('county', None),
            dateOfSale,
            timeOfSale,
            photo_url
        )

    else:
        # Handle the case where no details are available
        insert_address(address, None, None, None, None, None, None, None, None, None)

    return redirect(url_for('admin'))

@application.route('/submit_user', methods=['POST'])
def submit_user():
    # Extract form data
    username = request.form['username']
    password = request.form['password']
    email = request.form['email']
    phone = request.form['phone']
    role = request.form['role']
    stripe_customer_id = "NULL"

    # Hash the password
    hashed_password = generate_password_hash(password)

    # Connect to database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Insert new user
            sql = "INSERT INTO users (username, password, email, phone, role, stripe_customer_id) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(sql, (username, hashed_password, email, phone, role, stripe_customer_id))
        conn.commit()
    finally:
        conn.close()

    flash('User created successfully!')
    return redirect(url_for('admin'))

@application.route('/edit/<int:id>', methods=['GET'])
def edit_address(id):
    property = get_property_by_id(id)
    if property:
        print(property)  # Debugging statement to check the property details
        return render_template('edit_address.html', property=property)
    return 'Property not found', 404

@application.route('/update_address', methods=['POST'])
def update_address():
    # Retrieve the form data
    property_id = request.form['id']
    address = request.form['address']
    occupancy = request.form['occupancy']
    bedrooms = request.form['bedrooms']
    bathrooms = request.form['bathrooms']
    livingArea = request.form['livingArea']
    lotSize = request.form['lotSize']
    zpid = request.form['zpid']
    county = request.form['county']
    price = request.form['price']
    afterRehabValue = request.form['afterRehabValue']
    openingBid = request.form['openingBid']
    
    
    
    # Update the property in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = """
            UPDATE all_properties 
            SET addresses = %s, occupancy = %s, bedrooms = %s, bathrooms = %s, livingArea = %s, 
                lotSize = %s, zpid = %s, county = %s, price = %s, afterRehabValue = %s, openingBid = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (address, occupancy, bedrooms, bathrooms, livingArea, lotSize, zpid, county, price, afterRehabValue, openingBid, property_id))
        conn.commit()
    finally:
        conn.close()

    # Redirect to the admin page or another appropriate page
    user_role = session.get('user_role')
    if user_role == 2:
        return redirect(url_for('admin'))
    elif user_role == 1:
        return redirect(url_for('agent'))
    else:
        # Handle unexpected roles or if the user is not logged in
        return 'Unauthorized', 401

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

@application.route('/bid/<int:id>')
def bid(id):
    property = get_property_by_id(id)
    if property:
        formatted_price = "${:,.2f}".format(property['openingBid'])
        fee_amount = property['openingBid'] / 5
        formatted_fee = "${:,.2f}".format(fee_amount)
        total_amount = property['openingBid'] + fee_amount
        formatted_total = "${:,.2f}".format(total_amount)

        user_details = {
            'first_name': session.get('first_name', ''),
            'last_name': session.get('last_name', ''),
            'username': session.get('user_username', ''),
            'email': session.get('user_email', ''),
            'phone': session.get('user_phone', '')
            # Your user details logic
        }
        return render_template('bid.html', property=property, property_id=id, user=user_details,
                               formatted_price=formatted_price, formatted_fee=formatted_fee,
                               formatted_total=formatted_total)
    else:
        return 'Property not found', 404

@application.route('/submit_bid/<int:id>', methods=['POST'])
def submit_bid(id):
    # Extract user ID from session or form
    user_id = session['user_id']  # or from form data
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    username = request.form['username']
    email = request.form['email']
    bid_amount = request.form['maximum-bid-amount']
    phone = request.form['phone']

    # Get the bid amount from the form data (replace 'form_field_name' with the actual field name)

    bid_amount = request.form['maximum-bid-amount']

    # Insert bid into the database
    insert_bid(user_id, id, bid_amount)

    property = get_property_by_id(id)

    address = property['addresses']
    print(address)

    send_bid_receipt_email(address, email, first_name, last_name, bid_amount)
    send_bid_receipt_email_to_admin(phone, address, email, first_name, last_name, username, bid_amount)

    # Redirect to a confirmation page or back to the property details
    return redirect(url_for('property_details', id=id))

def insert_bid(user_id, property_id, bid_amount):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO bids (user_id, property_id, bid_progress, bid_amount) 
            VALUES (%s, %s, 'Pending', %s)
            """
            cursor.execute(sql, (user_id, property_id, bid_amount))
        conn.commit()
    finally:
        conn.close()

@application.route('/admin/bids')
def admin_bids():
    # Fetch bids from the database
    bids = get_all_bids_with_progress()  # Ensure this function is implemented to fetch bids

    return render_template('admin_bids.html', bids=bids)

def get_all_bids_with_progress():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Join the bids table with the users table
            cursor.execute("""
                SELECT b.id, b.property_id, b.bid_amount, b.bid_time, b.bid_progress, 
                       u.username, u.email, u.phone
            FROM bids b
            INNER JOIN users u ON b.user_id = u.id
            """)
        return cursor.fetchall()
    finally:
        conn.close()

@application.route('/delete_bid/<int:bid_id>', methods=['GET', 'POST'])
@requires_roles(2)  # Ensure only admins can access this route
def delete_bid(bid_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM bids WHERE id = %s", (bid_id,))
            conn.commit()
        flash('Bid deleted successfully!', 'success')
    except Exception as e:
        application.logger.error(f"Error deleting bid: {e}")
        flash('An error occurred while deleting the bid.', 'error')
    finally:
        if conn:
            conn.close()
        return redirect(url_for('admin_bids'))



@application.route('/update_bid_progress', methods=['POST'])
def update_bid_progress():
    bid_id = request.form['bid_id']
    new_status = request.form['new_status']

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE bids SET bid_progress = %s WHERE id = %s"
            cursor.execute(sql, (new_status, bid_id))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_bids'))

@application.route('/my_bids')
def my_bids():
    if 'user_id' not in session:
        return redirect(url_for('login_form'))  # Redirect to login if the user is not logged in

    user_id = session['user_id']
    bids = get_bids_by_user_id(user_id)  # Fetch bids for the logged-in user

    # Add property details to each bid
    for bid in bids:
        property_id = bid['property_id']
        property = get_property_by_id(property_id)
        bid['property_address'] = property['addresses'] if property else 'Unknown'

    return render_template('subscriber_bids.html', bids=bids)

def get_bids_by_user_id(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Assuming the table name is 'bids' and it has the columns 'id', 'user_id', 'property_id', etc.
            sql = "SELECT * FROM bids WHERE user_id = %s"
            cursor.execute(sql, (user_id,))
        return cursor.fetchall()
    finally:
        conn.close()

@application.route('/cancel_bid/<int:bid_id>', methods=['POST'])
def cancel_bid(bid_id):
    if 'user_id' not in session:
        return redirect(url_for('login_form'))  # Redirect to login if the user is not logged in

    user_id = session['user_id']

    # Check if the user has permission to cancel the bid
    if not can_user_cancel_bid(user_id, bid_id):
        flash('You do not have permission to cancel this bid.', 'error')
        return redirect(url_for('subscriber'))  # Redirect back to the user's bids page

    try:
        # Cancel the bid in the database
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "DELETE FROM bids WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (bid_id, user_id))
        conn.commit()
        flash('Bid cancelled successfully.', 'success')
    except Exception as e:
        # Log the error for debugging
        application.logger.error(f"Error cancelling bid: {e}")
        flash('An error occurred while cancelling the bid.', 'error')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('subscriber'))  # Redirect back to the user's bids page

# Helper function to check if the user can cancel the bid
def can_user_cancel_bid(user_id, bid_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id FROM bids WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (bid_id, user_id))
            bid = cursor.fetchone()
            return bid is not None
    finally:
        if conn:
            conn.close()
    return False



def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as file:
        pdf_reader = PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_auction_details(pdf_text):
    pattern = r'(DATE OF SALE: \d{1,2}/\d{1,2}/\d{2,4}|RESCHEDULED: \d{1,2}/\d{1,2}/\d{2,4})\s+Action:.*?\nTIME: (\d{1,2}:\d{2} (AM|PM)) Premises: (.*?) - (.*?)\n.*?FINAL JUDGMENT AS OF .*? - \$(\d{1,3}(?:,\d{3})*)'
    matches = re.findall(pattern, pdf_text, re.DOTALL)

    auction_details = []
    for date, time, am_pm, address_part1, address_part2, final_judgment in matches:
        cleaned_date = datetime.strptime(date.split(': ')[1], '%m/%d/%y').strftime('%Y-%m-%d')
        cleaned_time = f"{time} {am_pm}".strip()
        cleaned_address = f"{address_part1} - {address_part2}".strip()
        cleaned_final_judgment = int(final_judgment.replace(',', ''))  # Convert to integer

        auction_details.append((cleaned_address, cleaned_date, cleaned_time, cleaned_final_judgment))

    return auction_details

@application.template_filter('format_currency')
def format_currency(value):
    return "${:,.2f}".format(value) if value else 'N/A'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_photo(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_PHOTO

@application.route('/upload_pdf', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            

            print(f"File saved at {file_path}")  # Debug print
            process_pdf(file_path)

            flash('File successfully uploaded and processed')
            return redirect(url_for('admin'))
    return render_template('upload_pdf.html')

def process_pdf(file_path):
    pdf_text = extract_text_from_pdf(file_path)
    auction_details = extract_auction_details(pdf_text)

    for address, date_of_sale, time_of_sale, price in auction_details:
        try:
            property_id = check_address_exists(address)
            
            zpid = get_zpid_from_address(address) if not property_id else None
            details = get_property_details(zpid) if zpid else {}
            photo_url = get_photos(zpid) if zpid else None

            if property_id:
                update_property(
                    property_id, date_of_sale, time_of_sale, price
                )
                print(f"Updating Address: {address}, Date: {date_of_sale}, Time: {time_of_sale}, Price: {price}")
            else:
                insert_address(
                    address, zpid, details.get('bedrooms', None), details.get('bathrooms', None),
                    details.get('livingArea', None), details.get('lotSize', None), 
                    details.get('county', None), photo_url, date_of_sale, time_of_sale, price
                )
                print(f"Inserting New Address: {address}, Date: {date_of_sale}, Time: {time_of_sale}, Price: {price}")
        except Exception as e:
            print(f"Error processing address {address}: {e}")
            continue

    print("Processing of PDF completed.")


@application.route('/properties/<date>')
def properties_for_day(date):
    try:
        # Convert string date to datetime object
        selected_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return 'Invalid date format', 400

    # Fetch properties and their most recent photo for the selected date
    properties = get_properties_for_date_with_photos(selected_date)
    user_role = session.get('user_role')

    return render_template('propertiesforday.html', properties=properties, selected_date=selected_date, user_role=user_role)

def get_properties_for_date_with_photos(selected_date):
    conn = get_db_connection()
    properties_with_photos = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Adjusted query to ensure latest photo_url is fetched
            query = """
            SELECT p.*, pp.latest_photo_url
            FROM all_properties p
            LEFT JOIN (
                SELECT pp1.property_id, pp1.photo_url AS latest_photo_url
                FROM property_photos pp1
                INNER JOIN (
                    SELECT property_id, MAX(id) AS max_id
                    FROM property_photos
                    GROUP BY property_id
                ) pp2 ON pp1.property_id = pp2.property_id AND pp1.id = pp2.max_id
            ) pp ON p.id = pp.property_id
            WHERE p.dateOfSale = %s
            ORDER BY p.id;
            """
            cursor.execute(query, (selected_date,))
            properties_with_photos = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching properties with photos for date {selected_date}: {e}")
    finally:
        conn.close()
    return properties_with_photos


def get_properties_for_date(selected_date):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM all_properties WHERE dateOfSale = %s", (selected_date,))
            return cursor.fetchall()
    finally:
        conn.close()

def check_address_exists(address):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query_sql = "SELECT id FROM all_properties WHERE addresses = %s"
            cursor.execute(query_sql, (address,))
            result = cursor.fetchone()
            if result:
                return result[0]  # Access the first element of the tuple
            else:
                return None
    finally:
        conn.close()

@application.route('/upload_photo/<int:property_id>', methods=['POST'])
def upload_photo(property_id):
    # Ensure the upload folder exists
    if not os.path.exists(application.config['IMAGES_FOLDER']):
        os.makedirs(application.config['IMAGES_FOLDER'])

    if 'photo' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['photo']

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_photo(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config['IMAGES_FOLDER'], filename)
            file.save(file_path)
            insert_photo(property_id, file_path)
            flash('Photo uploaded successfully!')
        except Exception as e:
            flash(f"An error occurred: {e}")
            # Log the error for debugging
            application.logger.error(f"Error uploading file: {e}")
            print("Error uploading")
            return redirect(request.url)

    return redirect(url_for('manage_photos', property_id=property_id))

def insert_photo(property_id, photo_url):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO property_photos (property_id, photo_url) VALUES (%s, %s)"
            cursor.execute(sql, (property_id, photo_url))
        conn.commit()
        print(f"Photo inserted: {photo_url} for property {property_id}")  # Add this line
    finally:
        conn.close()

@application.route('/manage_photos/<int:property_id>', methods=['GET', 'POST'])
def manage_photos(property_id):
    if request.method == 'POST':
        if 'photo' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['photo']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config['IMAGES_FOLDER'], filename)
            file.save(file_path)

            insert_photo(property_id, file_path)
            flash('Photo uploaded successfully!')
            return redirect(url_for('manage_photos', property_id=property_id))

    photos = get_photos_by_property_id(property_id)
    print(f"Photos for property {property_id}: {photos}")  # Debug print

    return render_template('manage_photos.html', property_id=property_id, photos=photos)

@application.route('/delete_photo/<int:photo_id>', methods=['POST'])
def delete_photo(photo_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # SQL query to delete the photo with the given id
            query = "DELETE FROM property_photos WHERE id = %s"
            cursor.execute(query, (photo_id,))
        conn.commit()
        flash('Photo deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting photo with id {photo_id}: {e}")
        flash('Error deleting photo.', 'error')
    finally:
        conn.close()
    # Redirect back to the manage_photos page or another appropriate page
    return redirect(url_for('admin'))


YOUR_DOMAIN = 'https://www.bonaventurarealty.com'

@application.route('/create-checkout-session/<int:user_id>/<subscription_level>', methods=['GET', 'POST'])
def create_checkout_session(user_id, subscription_level):
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('User not found.')
            return redirect(url_for('register'))
    
        # Map the subscription level to the corresponding Stripe price ID
        price_ids = {
            #'test': 'price_1OYcdNFNut4X8qSwqIIX5Yz5',  
            'standard': 'price_1OYc4qFNut4X8qSwK07XJ8M2',
            'gold': 'price_1Of8KoFNut4X8qSwksIcg5js',
            'platinum': 'price_1Of8LFFNut4X8qSw1Kvnlavx',
        }
        selected_price_id = price_ids.get(subscription_level)


        success_url = url_for('checkout_success', user_id=user_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('checkout_cancel', user_id=user_id, _external=True)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                "price": selected_price_id,  # Assume selected_price_id is determined from the user's choice
                "quantity": 1
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={'user_id': str(user_id), 'subscription_level': subscription_level},
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        application.logger.error(f"Error in create_checkout_session: {e}")
        flash('An error occurred while creating the checkout session.')
        return redirect(url_for('show_registration_form'))

@application.route('/create-portal-session', methods=['POST'])
def customer_portal():
    # For demonstration purposes, we're using the Checkout session to retrieve the customer ID.
    # Typically this is stored alongside the authenticated user in your database.
    checkout_session_id = request.form.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)

    # This is the URL to which the customer will be redirected after they are
    # done managing their billing with the portal.
    return_url = YOUR_DOMAIN

    portalSession = stripe.billing_portal.Session.create(
        customer=checkout_session.customer,
        return_url=return_url,
    )
    return redirect(portalSession.url, code=303)

@application.route('/manage-portal', methods=['GET'])
def manage_portal():
    # User must be authenticated to view the customer portal
    if 'user_id' not in session:
        return redirect(url_for('login_form'))

    user_id = session['user_id']
    user = get_user_by_id(user_id)

    if not user or not user.get('stripe_customer_id'):
        flash('Stripe customer ID not found.')
        return redirect(url_for('login'))  # Redirect to a profile or error page

    try:
        # Create a new billing portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=user['stripe_customer_id'],
            return_url=YOUR_DOMAIN + '/login',
            
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        application.logger.error(f"Error creating billing portal session: {e}")
        flash('An error occurred while creating the billing portal session.')
        return redirect(url_for('login'))  # Redirect to a profile or error page



@application.route('/webhook', methods=['POST'])
def webhook_received():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = 'whsec_Bpp16lnFgIta80peknafbf0lPFQhwiyK'

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

        # Handle the event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            # Extract user ID from session metadata
            user_id = session['metadata']['user_id']
            
            

            # Update user with Stripe Customer ID
            update_user_with_stripe_id(user_id, session['customer'])

        return jsonify({'status': 'success'}), 200
    except ValueError:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return 'Invalid signature', 400
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


def update_user_with_stripe_id(user_id, stripe_customer_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Update SQL query to set both stripe_customer_id and subscription_level
            update_sql = """
            UPDATE users
            SET stripe_customer_id = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (stripe_customer_id, user_id))
        conn.commit()
    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
    finally:
        conn.close()

@application.route('/checkout_success/<int:user_id>')
def checkout_success(user_id):
    # Process successful checkout, e.g., update user status in DB
    # Redirect to login page
    session_id = request.args.get('session_id')
    return redirect(url_for('login_form'))

@application.route('/checkout_cancel/<int:user_id>')
def checkout_cancel(user_id):
    # Handle checkout cancellation, e.g., notify user or log
    return "Checkout cancelled. Please try again."

import logging
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_email_message(app_id, sender, to_addresses, subject, html_message):
    pinpoint_client = boto3.client('pinpoint', region_name='us-east-1')
    try:
        response = pinpoint_client.send_messages(
            ApplicationId=app_id,
            MessageRequest={
                "Addresses": {
                    address: {"ChannelType": "EMAIL"} for address in to_addresses
                },
                "MessageConfiguration": {
                    "EmailMessage": {
                        "FromAddress": sender,
                        "SimpleEmail": {
                            "Subject": {
                                "Charset": "UTF-8",
                                "Data": subject
                            },
                            "HtmlPart": {
                                "Charset": "UTF-8",
                                "Data": html_message
                            },
                            "TextPart": {
                                "Charset": "UTF-8",
                                "Data": "Text version of the email content"
                            }
                        }
                    }
                }
            }
        )
    except ClientError as e:
        logger.exception("Couldn't send email via Pinpoint: %s", e)
        return None
    else:
        return response['MessageResponse']['Result']

def send_bid_receipt_email(address, email, first_name, last_name, bid_amount):
    app_id = 'abccb22dc4414fe0b229357f51a1cdde'  
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    to_addresses = [email]
    subject = 'Confirmation of Bid'
    
    html_message = f"""
    <html>
        <head></head>
        <body>
            <p>Dear {first_name},</p>
            <p>Thank you for your bid of ${bid_amount} on {address}.</p>
            <p>Should you have any questions or need further assistance, please do not hesitate to reach out. Our dedicated team of professionals is here to provide you with personalized support every step of the way.</p>
            <p>Thank you for your continued trust in Bonaventura Realty. We look forward to helping you achieve your real estate goals.</p>
            <p>Warm regards,</p>
            <p>Bonaventura Realty Team</p>
        </body>
    </html>
    """


    message_ids = send_email_message(app_id, sender, to_addresses, subject, html_message)
    return message_ids

def send_bid_receipt_email_to_admin(phone, address, email, first_name, last_name, username, bid_amount):
    app_id = 'abccb22dc4414fe0b229357f51a1cdde'  
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    to_addresses = ['dstagge@bonaventurarealty.com']
    subject = f"Notification of Bid on {address}"
    
    html_message = f"""
    <html>
        <head></head>
        <body>
            <p>{first_name} {last_name} placed bid on {address}.</p>
            <p>Maximum Bid Amount: {bid_amount}</p>
            <p>{first_name} {last_name}'s Email: {email}</p>
            <p>{first_name} {last_name}'s Phone: {phone}</p>
            <p>{first_name} {last_name}'s Username: {username}</p>
        </body>
    </html>
    """


    message_ids = send_email_message(app_id, sender, to_addresses, subject, html_message)
    return message_ids

        

 
if __name__ == "__main__":
    application.run(port=4242)
    #To the next developer,
    #Good luck.. haha.
    #From Drew


