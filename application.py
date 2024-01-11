from flask import Flask, request, render_template, redirect, url_for
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
application = Flask(__name__)
load_dotenv()

stripe.api_key = 'your_stripe_secret_key'
application.secret_key = os.environ.get('SECRET_KEY')

UPLOAD_FOLDER = 'static/pdfs' 
ALLOWED_EXTENSIONS = {'pdf'}

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
    
    return render_template('subscriber.html', properties_by_date=properties_by_date_with_day, counties=counties, selected_county=county_filter)

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
    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    # Filter properties by selected county
    if selected_county:
        properties = [prop for prop in properties if prop.get('county') == selected_county]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop('year', None)
    calendar_data.pop('month', None)

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
        return redirect(url_for('profile'))

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
        return redirect(url_for('home'))

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
            sql = "UPDATE users SET username = %s, email = %s, phone = %s WHERE id = %s"
            cursor.execute(sql, (username, email, phone, user_id))
        conn.commit()
    finally:
        conn.close()

    flash('User updated successfully!')
    return redirect(url_for('subscriber'))

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
        session['user_email'] = user['email'] 
        session['user_username'] = user['username'] # Store user email in session
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
        fee_amount = property['price'] / 10
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
    # Here you would handle the bid submission
    # For example, save the bid to the database

    username = request.form['username']
    email = request.form['email']
    phone = request.form['phone']
    bid_amount = request.form['bid']

    # Save the bid information to the database or process it as needed

    # Redirect to a confirmation page or back to the property details
    return redirect(url_for('property_details', id=id))

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



@application.route('/upload_photo/<int:id>', methods=['POST'])
def upload_photo(id):
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

        update_photo_url(id, file_path)
        return redirect(url_for('admin'))

def update_photo_url(property_id, photo_url):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE all_properties SET photo_url = %s WHERE id = %s"
            cursor.execute(sql, (photo_url, property_id))
        conn.commit()
    finally:
        conn.close()

@application.route('/properties/<date>')
def properties_for_day(date):
    try:
        # Convert string date to datetime object
        selected_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return 'Invalid date format', 400

    # Fetch properties for the selected date
    properties = get_properties_for_date(selected_date)
    return render_template('propertiesforday.html', properties=properties, selected_date=selected_date)

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



        



if __name__ == "__main__":
    application.run()
    #To the next developer,
    #Good luck.. haha.
    #From Drew

