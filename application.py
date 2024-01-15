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
ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_EXTENSIONS_PHOTO = {'png', 'jpg', 'jpeg', 'gif'}

application.config['UPLOAD_FOLDER'] = 'static/pdfs'

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
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT photo_url FROM property_photos WHERE property_id = %s", (property_id,))
            return cursor.fetchall()
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
        delete_user(user_id)

        flash('Subscription and user deleted successfully.')
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
    email = request.form['email']
    phone = request.form['phone']

    # Update user details in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = "UPDATE users SET email = %s, phone = %s WHERE id = %s"
            cursor.execute(update_sql, (email, phone, user_id))
        conn.commit()
    finally:
        conn.close()

    flash('User updated successfully!')

    # Redirect based on user role
    user_role = session.get('user_role')
    if user_role == 0:
        return redirect(url_for('subscriber'))
    elif user_role == 1:
        return redirect(url_for('agent'))
    elif user_role == 2:
        return redirect(url_for('admin'))
    else:
        # Default redirect if role is undefined or unexpected
        return redirect(url_for('home'))




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
        session['user_id'] = user['id']  # Store user ID in session
        session['user_email'] = user['email'] 
        session['user_username'] = user['username'] # Store user email in session
        session['user_phone'] = user['phone']  # Store user phone in session
        session['user_role'] = user['role']
        session['stripe_customer_id'] = user['stripe_customer_id']
        if user['role'] == 0:  # Assuming 0 is the role for subscribers
            if not check_active_subscription(user):
                flash('Your subscription is inactive. Please renew to continue.')
                return redirect(url_for('pricing'))  # Redirect to subscription page
            else:
                return redirect(url_for('subscriber'))
        elif user['role'] == 1:
            return redirect(url_for('agent'))
        elif user['role'] == 2:
            return redirect(url_for('admin'))
        else:
            return 'Invalid role', 401
    else:
        return 'Invalid credentials', 401

def check_active_subscription(user):
    stripe_customer_id = user.get('stripe_customer_id')
    if not stripe_customer_id:
        # Handle cases where stripe_customer_id is not available
        application.logger.error("Stripe customer ID not found for user.")
        return False

    try:
        subscriptions = stripe.Subscription.list(customer=stripe_customer_id, status='active')
        return any(subscriptions.data)
    except InvalidRequestError as e:
        # Handle Stripe API errors
        application.logger.error(f"Error checking active subscription: {e}")
        return False


@application.route('/register', methods=['GET'])
def show_registration_form():
    return render_template('create_user.html')

from stripe.error import StripeError

@application.route('/register_user', methods=['POST'])
def register_user():
    try:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form['phone']
        role = request.form['role']

        # Create a new customer in Stripe
        stripe_customer = stripe.Customer.create(
            email=email,
            name=username,
            phone=phone
        )

        # Get the Stripe customer ID
        stripe_customer_id = stripe_customer["id"]

        # Create user in the database with Stripe customer ID
        user_id = create_user_in_db(username, password, email, phone, role, stripe_customer_id)

        return redirect(url_for('create_checkout_session', user_id=user_id), code=307)
    except StripeError as e:
        # Handle errors from Stripe
        flash(f"Stripe error: {e.user_message}")
        return redirect(url_for('show_registration_form'))
    except Exception as e:
        # Handle other errors
        flash(f"An error occurred: {e}")
        return redirect(url_for('show_registration_form'))

def create_user_in_db(username, password, email, phone, role, stripe_customer_id):
    # Your existing database logic to create a user, now including stripe_customer_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password, email, phone, role, stripe_customer_id) VALUES (%s, %s,%s, %s, %s, %s)",
                   (username, generate_password_hash(password), email, phone, role, stripe_customer_id))
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return user_id


    
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
        print(property)  # Debugging statement to check the property details
        return render_template('edit_address.html', property=property)
    return 'Property not found', 404

@application.route('/update_address', methods=['POST'])
def update_address():
    # Retrieve the form data
    property_id = request.form['id']
    address = request.form['address']
    zpid = request.form['zpid']
    bedrooms = request.form['bedrooms']
    bathrooms = request.form['bathrooms']
    livingArea = request.form['livingArea']
    lotSize = request.form['lotSize']
    dateOfSale = request.form['dateOfSale']
    timeOfSale = request.form['timeOfSale']
    county = request.form['county']

    # Update the property in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = """
            UPDATE all_properties 
            SET addresses = %s, zpid = %s, bedrooms = %s, bathrooms = %s, livingArea = %s, 
                lotSize = %s, county = %s , timeOfSale = %s, dateOfSale = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (address, zpid, bedrooms, bathrooms, livingArea, lotSize, county, dateOfSale, timeOfSale, property_id))
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
        formatted_price = "${:,.2f}".format(property['price'])
        fee_amount = property['price'] / 5
        formatted_fee = "${:,.2f}".format(fee_amount)
        total_amount = property['price'] + fee_amount
        formatted_total = "${:,.2f}".format(total_amount)

        user_details = {
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

    # Get the bid amount from the form data (replace 'form_field_name' with the actual field name)
    bid_amount = request.form['bid_amount']

    # Insert bid into the database
    insert_bid(user_id, id, bid_amount)

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

    # Fetch properties for the selected date
    properties = get_properties_for_date(selected_date)

    # Apply photo display logic to each property
    for property in properties:
        if property['photo_url'] and 'maps.googleapis.com/maps/api/streetview' not in property['photo_url']:
            property['display_photo_url'] = property['photo_url']
        else:
            latest_photo = get_latest_photo_by_property_id(property['id'])
            if latest_photo:
                property['display_photo_url'] = latest_photo['photo_url']
            else:
                property['display_photo_url'] = None  # Or a default image URL
    user_role = session.get('user_role')

    return render_template('propertiesforday.html', properties=properties, selected_date=selected_date, user_role=user_role)


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
    if not os.path.exists(application.config['UPLOAD_FOLDER']):
        os.makedirs(application.config['UPLOAD_FOLDER'])

    if 'photo' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['photo']

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            insert_photo(property_id, file_path)
            flash('Photo uploaded successfully!')
        except Exception as e:
            flash(f"An error occurred: {e}")
            # Log the error for debugging
            application.logger.error(f"Error uploading file: {e}")
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
            file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            insert_photo(property_id, file_path)
            flash('Photo uploaded successfully!')
            return redirect(url_for('manage_photos', property_id=property_id))

    photos = get_photos_by_property_id(property_id)
    print(f"Photos for property {property_id}: {photos}")  # Debug print

    return render_template('manage_photos.html', property_id=property_id, photos=photos)

def get_properties_with_latest_photo():
    properties = get_all_properties()
    for property in properties:
        # Check if property's photo_url is valid and not a Google Maps URL
        if property['photo_url'] and 'maps.googleapis.com/maps/api/streetview' not in property['photo_url']:
            property['display_photo_url'] = property['photo_url']
        else:
            # Fetch the latest uploaded photo for the property
            latest_photo = get_latest_photo_by_property_id(property['id'])
            if latest_photo:
                property['display_photo_url'] = latest_photo['photo_url']
            else:
                # Set to a default image URL or None
                property['display_photo_url'] = None  # or the path to a default image
        

    return properties


def get_latest_photo_by_property_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT photo_url FROM property_photos WHERE property_id = %s ORDER BY id DESC LIMIT 1", (property_id,))
            latest_photo = cursor.fetchone()
            print(f"Latest photo for property {property_id}: {latest_photo}")  # Debug print
            return latest_photo
    finally:
        conn.close()


YOUR_DOMAIN = 'http://localhost:8000'

@application.route('/create-checkout-session/<int:user_id>', methods=['POST'])
def create_checkout_session(user_id):
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('User not found.')
            return redirect(url_for('register'))

        # Use the existing Stripe customer ID
        checkout_session = stripe.checkout.Session.create(
            customer=user['stripe_customer_id'],
            payment_method_types=['card'],
            line_items=[{"price": 'price_1OYc4qFNut4X8qSwK07XJ8M2', "quantity": 1}],
            mode='subscription',
            success_url=url_for('checkout_success', user_id=user_id, _external=True),
            cancel_url=url_for('checkout_cancel', user_id=user_id, _external=True),
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

@application.route('/webhook', methods=['POST'])
def webhook_received():
    # Replace this endpoint secret with your endpoint's unique secret
    # If you are testing with the CLI, find the secret by running 'stripe listen'
    # If you are using an endpoint defined with the API or dashboard, look in your webhook settings
    # at https://dashboard.stripe.com/webhooks
    webhook_secret = 'whsec_12345'
    request_data = json.loads(request.data)

    if webhook_secret:
        # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
        signature = request.headers.get('stripe-signature')
        try:
            event = stripe.Webhook.construct_event(
                payload=request.data, sig_header=signature, secret=webhook_secret)
            data = event['data']
        except Exception as e:
            return e
        # Get the type of webhook event sent - used to check the status of PaymentIntents.
        event_type = event['type']
    else:
        data = request_data['data']
        event_type = request_data['type']
    data_object = data['object']

    print('event ' + event_type)

    if event_type == 'checkout.session.completed':
        print('🔔 Payment succeeded!')
    elif event_type == 'customer.subscription.trial_will_end':
        print('Subscription trial will end')
    elif event_type == 'customer.subscription.created':
        print('Subscription created %s', event.id)
    elif event_type == 'customer.subscription.updated':
        print('Subscription created %s', event.id)
    elif event_type == 'customer.subscription.deleted':
        # handle subscription canceled automatically based
        # upon your subscription settings. Or if the user cancels it.
        print('Subscription canceled: %s', event.id)

    return jsonify({'status': 'success'})

@application.route('/checkout_success/<int:user_id>')
def checkout_success(user_id):
    # Process successful checkout, e.g., update user status in DB
    # Redirect to login page
    return redirect(url_for('login_form'))

@application.route('/checkout_cancel/<int:user_id>')
def checkout_cancel(user_id):
    # Handle checkout cancellation, e.g., notify user or log
    return "Checkout cancelled. Please try again."

if __name__ == "__main__":
    application.run()
    #To the next developer,
    #Good luck.. haha.
    #From Drew

