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
import re
from PyPDF2 import PdfReader
from datetime import datetime, timedelta
import calendar

application = Flask(__name__)
load_dotenv()

application.secret_key = os.environ.get("SECRET_KEY")

UPLOAD_FOLDER = "static/pdfs"
IMAGES_FOLDER = "static/images"
ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_EXTENSIONS_PHOTO = {"png", "jpg", "jpeg"}

application.config["UPLOAD_FOLDER"] = "static/pdfs"
application.config["IMAGES_FOLDER"] = "static/images"


def format_currency(value):
    # Assuming value might be a string with spaces, e.g., "500 000"
    if isinstance(value, str):
        value = value.replace(" ", "")  # Remove spaces
    number = float(value)
    return "${:,.2f}".format(number)


# Register the filter with your Jinja environment
application.jinja_env.filters["format_currency"] = format_currency


def split_address(address):
    return address.split(" - ")[0]


# Register the filter with Jinja
application.jinja_env.filters["split_address"] = split_address


def split_city(address):
    return address.split(" - ")[1]


# Register the filter with Jinja
application.jinja_env.filters["split_city"] = split_city


def requires_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_role" not in session or session["user_role"] not in roles:
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return wrapped

    return wrapper


# Database Helper Functions
def get_db_connection():
    return pymysql.connect(
        host=os.environ.get("database_host"),
        user=os.environ.get("database_user"),
        password=os.environ.get("database_password"),
        db=os.environ.get("database_db"),
        port=3306,
    )


def insert_address(
    address,
    zpid,
    bedrooms,
    bathrooms,
    livingArea,
    lotSize,
    county,
    photo_url,
    date_of_sale,
    time_of_sale,
    price,
):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            insert_sql = """
            INSERT INTO all_properties 
            (addresses, zpid, bedrooms, bathrooms, livingArea, lotSize, county, photo_url, dateOfSale, timeOfSale, price) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_sql,
                (
                    address,
                    zpid,
                    bedrooms,
                    bathrooms,
                    livingArea,
                    lotSize,
                    county,
                    photo_url,
                    date_of_sale,
                    time_of_sale,
                    price,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_all_properties():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Include price in the SELECT query
            cursor.execute(
                "SELECT id, addresses, bedrooms, bathrooms, livingArea, lotSize, county, dateOfSale, timeOfSale, photo_url, price FROM all_properties"
            )
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
            photos = (
                cursor.fetchall()
            )  # Fetch all photo entries matching the property_id
    except Exception as e:
        print(f"Error fetching photos for property_id {property_id}: {e}")
    finally:
        conn.close()
    return photos


def get_interior_photos_by_property_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM interior_photos WHERE property_id = %s", (property_id,)
            )
            return cursor.fetchall()
    finally:
        conn.close()


def get_unique_counties():
    conn = get_db_connection()
    try:
        # Get today's date in the format that matches your database's date format
        today = datetime.now().strftime('%Y-%m-%d')
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Adjust the SQL query to filter by dateOfSale
            query = """
                SELECT DISTINCT county 
                FROM all_properties 
                WHERE county IS NOT NULL 
                AND dateOfSale >= %s
            """
            cursor.execute(query, (today,))
            return [row["county"] for row in cursor.fetchall()]
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
            delete_interior_photos_sql = "DELETE FROM interior_photos WHERE property_id = %s"
            cursor.execute(delete_interior_photos_sql, (property_id,))

            delete_photos_sql = "DELETE FROM property_photos WHERE property_id = %s"
            cursor.execute(delete_photos_sql, (property_id,))
            
            delete_property_sql = "DELETE FROM all_properties WHERE id = %s"
            cursor.execute(delete_property_sql, (property_id,))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_zpid_from_address(address):
    conn = http.client.HTTPSConnection("zillow56.p.rapidapi.com")
    headers = {
        "X-RapidAPI-Key": os.environ.get("X-RapidAPI-Key"),
        "X-RapidAPI-Host": os.environ.get("X-RapidAPI-Host"),
    }
    # Clean the address by removing newline characters and other potential control characters
    cleaned_address = re.sub(r"\s+", " ", address.strip())
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
        "X-RapidAPI-Key": os.environ.get("X-RapidAPI-Key"),
        "X-RapidAPI-Host": os.environ.get("X-RapidAPI-Host"),
    }

    conn.request("GET", f"/property?zpid={zpid}", headers=headers)
    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))

    # Define a helper function to handle None values
    def get_value_or_placeholder(key, placeholder="--"):
        value = response_json.get(key)
        return value if value is not None else placeholder

    bedrooms = get_value_or_placeholder("bedrooms")
    bathrooms = get_value_or_placeholder("bathrooms")
    livingArea = get_value_or_placeholder("livingArea")
    lotSize = get_value_or_placeholder("lotSize")
    county = get_value_or_placeholder("county")

    return {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "livingArea": livingArea,
        "lotSize": lotSize,
        "county": county,
    }


@application.route("/")
def home():
    today = datetime.today()
    current_date = today.strftime("%Y-%m-%d")
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    selected_county = request.args.get("county", type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime("%B")

    properties = get_all_properties()  # Fetch all properties
    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    # Filter properties by selected county
    if selected_county:
        properties = [
            prop for prop in properties if prop.get("county") == selected_county
        ]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop("year", None)
    calendar_data.pop("month", None)

    return render_template(
        "index.html",
        current_month=current_month,
        year=year,
        month=month,
        current_date=current_date,
        selected_county=selected_county,
        counties=counties,
        **calendar_data,
    )


@application.route("/pricing")
def pricing():
    return render_template("pricing.html")


@application.route("/subscriber_agreement")
def subscriber_agreement():
    return render_template("subscriber_agreement.html")



@application.route("/services")
def services():
    return render_template("services.html")

@application.route("/subscriber")
@requires_roles(0)
def subscriber():
    user_id = session.get("user_id")
    if not user_id:
        # Handle the case where there is no user logged in
        flash("You need to be logged in to view this page.")
        return redirect(url_for("login_form"))
    today = datetime.today()
    current_date = today.strftime("%Y-%m-%d")
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    selected_county = request.args.get("county", type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime("%B")
    properties = get_all_properties()  # Fetch all properties
    counties = get_unique_counties()
    # Fetch all properties with their latest photo URLs

    if selected_county:
        properties = [
            prop for prop in properties if prop.get("county") == selected_county
        ]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop("year", None)
    calendar_data.pop("month", None)

    counties = get_unique_counties()  # Fetch unique counties for filter dropdown
    user = get_user_by_id(user_id)
    return render_template(
        "subscriber.html",
        user=user,
        current_month=current_month,
        year=year,
        month=month,
        current_date=current_date,
        selected_county=selected_county,
        counties=counties,
        **calendar_data,
    )


@application.route("/agent")
@requires_roles(1)
def agent():
    today = datetime.today()
    current_date = today.strftime("%Y-%m-%d")
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    # here is the county selector what argument is gotten
    selected_county = request.args.get("county", type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime("%B")
    properties = get_all_properties()  # Fetch all properties
    # fetch whole list of counties here
    counties = get_unique_counties()

    # displays properties in that county if argument gotten
    if selected_county:
        properties = [
            prop for prop in properties if prop.get("county") == selected_county
        ]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop("year", None)
    calendar_data.pop("month", None)

    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    return render_template(
        "agent.html",
        current_month=current_month,
        year=year,
        month=month,
        current_date=current_date,
        selected_county=selected_county,
        counties=counties,
        **calendar_data,
    )


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
        prop_date = prop["dateOfSale"]
        if isinstance(prop_date, str):
            prop_date = datetime.strptime(prop_date, "%Y-%m-%d").date()
        if prop_date.year == year and prop_date.month == month:
            properties_by_date[prop_date.day].append(prop)

    return {
        "year": year,
        "month": month,
        "first_weekday": first_weekday,
        "days_in_month": days_in_month,
        "properties_by_date": properties_by_date,
    }


@application.route("/admin")
@requires_roles(2)
def admin():
    today = datetime.today()
    current_date = today.strftime("%Y-%m-%d")
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    # here is the county selector what argument is gotten
    selected_county = request.args.get("county", type=str)

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    year = max(1900, min(year, 2100))
    current_month = datetime(year, month, 1).strftime("%B")
    properties = get_all_properties()  # Fetch all properties
    # fetch whole list of counties here
    counties = get_unique_counties()

    # displays properties in that county if argument gotten
    if selected_county:
        properties = [
            prop for prop in properties if prop.get("county") == selected_county
        ]

    calendar_data = generate_calendar(year, month, properties)

    # Remove 'year' and 'month' from calendar_data to prevent duplication
    calendar_data.pop("year", None)
    calendar_data.pop("month", None)

    counties = get_unique_counties()  # Fetch unique counties for filter dropdown

    return render_template(
        "admin.html",
        current_month=current_month,
        year=year,
        month=month,
        current_date=current_date,
        selected_county=selected_county,
        counties=counties,
        **calendar_data,
    )


@application.route("/admin_usercontrol", methods=["GET"])
@requires_roles(2)
def admin_usercontrol():
    users = get_all_users()
    county_filter = request.args.get("county")
    counties = get_unique_counties()
    return render_template(
        "admin_usercontrol.html",
        users=users,
        counties=counties,
        selected_county=county_filter,
    )

@application.route('/admin/update_password', methods=['POST'])
def admin_update_password():
    # You may want to include additional checks to verify the user's role is admin
    username = request.form['username']
    new_password = request.form['new_password']

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check if the username exists
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            user_id = cursor.fetchone()
            if user_id:
                # Proceed with updating the password
                new_password_hash = generate_password_hash(new_password)
                cursor.execute('UPDATE users SET password = %s WHERE username = %s', (new_password_hash, username))
                conn.commit()
                flash('Password updated successfully.', 'success')
            else:
                # Username does not exist
                flash('Username not found.', 'danger')
    except Exception as e:
        # Log the exception; for simplicity, just flash a message here
        flash(f'An error occurred: {e}', 'danger')
    finally:
        conn.close()

    # Redirect to the admin page or wherever is appropriate
    return redirect(url_for('admin_usercontrol'))

@application.route('/admin/show_update_password_form', methods=['GET'])
def show_admin_update_password_form():
    # Add any required logic here, for example, verifying that the user is an admin
    return render_template('admin_update_password.html')

@application.route('/update_password', methods=['POST'])
def subscriber_update_password():
    # You may want to include additional checks to verify the user's role is admin
    username = request.form['username']
    new_password = request.form['new_password']

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check if the username exists
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            user_id = cursor.fetchone()
            if user_id:
                # Proceed with updating the password
                new_password_hash = generate_password_hash(new_password)
                cursor.execute('UPDATE users SET password = %s WHERE username = %s', (new_password_hash, username))
                conn.commit()
                flash('Password updated successfully.', 'success')
            else:
                # Username does not exist
                flash('Username not found.', 'danger')
    except Exception as e:
        # Log the exception; for simplicity, just flash a message here
        flash(f'An error occurred: {e}', 'danger')
    finally:
        conn.close()

    # Redirect to the admin page or wherever is appropriate
    return redirect(url_for('login_form'))

@application.route('/show_update_password_form', methods=['GET'])
def show_subscriber_update_password_form():
    # Add any required logic here, for example, verifying that the user is an admin
    return render_template('update_password.html')


@application.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("login_form"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)

    if request.method == "GET":
        return render_template("edit_profile.html", user=user)
    else:
        # Get data from form
        username = request.form["username"]
        email = request.form["email"]
        phone = request.form["phone"]
        # Update user information in the database
        update_user(user_id, username, email, phone)
        return redirect(url_for("login_form"))


@application.route("/delete_user/<int:user_id>", methods=["GET"])
def delete_user(user_id):
    conn = get_db_connection()
    try:
        # Retrieve the user to get the Stripe customer ID
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

        # Now delete the user from the database
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        flash("User and Stripe customer deleted successfully!")
    except Exception as e:
        flash(f"An error occurred: {e}")
    finally:
        conn.close()

    return redirect(url_for("admin_usercontrol"))


@application.route("/edit_user/<int:user_id>", methods=["GET"])
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
        return render_template("edit_user.html", user=user)
    else:
        flash("User not found.")
        return redirect(url_for("admin_usercontrol"))


@application.route("/update_user/<int:user_id>", methods=["POST"])
def update_user(user_id):
    # Extract form data
    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    username = request.form["username"]
    email = request.form["email"]
    phone = request.form["phone"]

    # Update user details in the database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = "UPDATE users SET first_name = %s, last_name = %s, username = %s, email = %s, phone = %s WHERE id = %s"
            cursor.execute(
                update_sql, (first_name, last_name, username, email, phone, user_id)
            )
        conn.commit()
    finally:
        conn.close()

    flash("User updated successfully!")

    # Redirect based on user role

    return redirect(url_for("login_form"))


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


@application.route("/property/<int:id>")
def property_details(id):
    property = get_property_with_latest_photo(
        id
    )  # Make sure this function exists and fetches the data correctly
    interior_photos = get_interior_photos_by_property_id(id)  # Fetch interior photos

    if not property:
        return "Property not found", 404

    return render_template(
        "property_details.html", property=property, interior_photos=interior_photos
    )


def get_property_with_latest_photo(property_id):
    conn = get_db_connection()
    property_with_photo = None
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Query to fetch the property details and latest photo_url for a specific property ID
            query = """
            SELECT p.*, pp.latest_photo_url
            FROM all_properties p
            LEFT JOIN (
                SELECT pp1.property_id, pp1.photo_url AS latest_photo_url
                FROM property_photos pp1
                INNER JOIN (
                    SELECT property_id, MAX(id) AS max_id
                    FROM property_photos
                    WHERE property_id = %s  # Filter by the specific property ID
                    GROUP BY property_id
                ) pp2 ON pp1.property_id = pp2.property_id AND pp1.id = pp2.max_id
            ) pp ON p.id = pp.property_id
            WHERE p.id = %s;  # Filter for the specific property ID
            """
            cursor.execute(query, (property_id, property_id))
            property_with_photo = (
                cursor.fetchone()
            )  # Since it's only one property, we use fetchone()
    except Exception as e:
        print(f"Error fetching property with photo for property ID {property_id}: {e}")
    finally:
        conn.close()
    return property_with_photo


def get_latest_photo_by_property_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Assuming there's a 'created_at' or similar timestamp field you can sort by
            # If not, you can sort by 'id' assuming higher IDs are newer
            query = """
                SELECT id, photo_url 
                FROM property_photos 
                WHERE property_id = %s
                ORDER BY id DESC  # or 'created_at DESC'
                LIMIT 1
            """
            cursor.execute(query, (property_id,))
            photo = cursor.fetchone()  # Fetch the most recent photo entry
            return photo
    except Exception as e:
        print(f"Error fetching the latest photo for property_id {property_id}: {e}")
        return None
    finally:
        conn.close()


@application.route("/login", methods=["GET"])
def login_form():
    return render_template("login.html")


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


@application.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        # Username does not exist
        flash("Invalid username. Please try again.", "error")
        return redirect(url_for("login_form"))

    if not check_password_hash(user["password"], password):
        # Password is incorrect
        flash("Wrong password. Please try again.", "error")
        return redirect(url_for("login_form"))

    # Set user session info here if login is successful
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["first_name"] = user["first_name"]
    session["last_name"] = user["last_name"]
    session["user_phone"] = user["phone"]
    session["user_role"] = user["role"]
    session["user_username"] = user["username"]

    # Redirect based on user role
    if user["role"] in [1, 2]:  # Assuming 1 is for agents and 2 is for admins
        return redirect(url_for("admin") if user["role"] == 2 else url_for("agent"))
    elif user["role"] == 0:
        return redirect(url_for("subscriber"))
    else:
        return redirect(url_for("pricing"))





@application.route("/register", methods=["GET"])
def show_registration_form():
    return render_template("create_user.html")


def create_user_in_db(first_name, last_name, username, password, email, phone, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (first_name, last_name, username, password, email, phone, role) VALUES (%s, %s, %s, %s,%s, %s, %s, %s)",
        (
            first_name,
            last_name,
            username,
            generate_password_hash(password),
            email,
            phone,
            role,
        ),
    )
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


@application.route("/check_username", methods=["POST"])
def check_username():
    username = request.form["username"]
    if username_exists(username):
        return jsonify({"exists": True})
    return jsonify({"exists": False})


@application.route("/logout")
def logout():
    session.pop("user_role", None)  # Remove the user role from session
    return redirect(url_for("home"))


@application.route("/add_address", methods=["GET"])
def add_address():
    return render_template("add_address.html")


@application.route("/add_user", methods=["GET"])
def add_user():
    return render_template("add_user.html")


@application.route("/submit_address", methods=["POST"])
def submit_address():
    address = request.form["address"]
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
            details.get("bedrooms", None),
            details.get("bathrooms", None),
            details.get("livingArea", None),
            details.get("lotSize", None),
            details.get("county", None),
            dateOfSale,
            timeOfSale,
            photo_url,
        )

    else:
        # Handle the case where no details are available
        insert_address(address, None, None, None, None, None, None, None, None, None)

    return redirect(url_for("admin"))


@application.route("/submit_user", methods=["POST"])
def submit_user():
    # Extract form data
    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    username = request.form["username"]
    password = request.form["password"]
    email = request.form["email"]
    phone = request.form["phone"]
    role = request.form["role"]

    # Hash the password
    hashed_password = generate_password_hash(password)

    # Connect to database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Insert new user
            sql = "INSERT INTO users (first_name, last_name, username, password, email, phone, role) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(
                sql,
                (first_name, last_name, username, hashed_password, email, phone, role),
            )
        conn.commit()
    finally:
        conn.close()

    flash("User created successfully!")
    return redirect(url_for("admin_usercontrol"))


@application.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_address(id):
    # Fetch property details
    property = get_property_by_id(id)
    photos = get_photos_by_property_id(id)  # Fetch existing photos
    interior_photos = get_interior_photos_by_property_id(id)

    if request.method == "POST":
        # Handle photo upload
        if "photo" in request.files:
            file = request.files["photo"]
            if file.filename == "" or not allowed_photo(file.filename):
                flash("Invalid file or no file selected", "error")
            else:
                filename = secure_filename(file.filename)
                file_path = os.path.join(application.config["IMAGES_FOLDER"], filename)
                file.save(file_path)
                insert_photo(id, file_path)  # Assuming this function exists
                flash("Photo uploaded successfully!", "success")
                return redirect(
                    url_for("edit_address", id=id)
                )  # Reload the page to show the new photo

        # Additional POST handling, e.g., updating property details
        # This part depends on how you handle property updates (not shown here)

    if not property:
        return "Property not found", 404

    # Render the template, passing property and photos
    return render_template(
        "edit_address.html",
        property=property,
        photos=photos,
        interior_photos=interior_photos,
    )


@application.route("/update_address", methods=["POST"])
def update_address():
    # Retrieve the form data
    property_id = request.form["id"]
    address = request.form["address"]
    occupancy = request.form["occupancy"]
    bedrooms = request.form["bedrooms"]
    bathrooms = request.form["bathrooms"]
    livingArea = request.form["livingArea"]
    lotSize = request.form["lotSize"]
    zpid = request.form["zpid"]
    county = request.form["county"]
    price = request.form["price"]
    afterRehabValue = request.form["afterRehabValue"]
    openingBid = request.form["openingBid"]

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
            cursor.execute(
                update_sql,
                (
                    address,
                    occupancy,
                    bedrooms,
                    bathrooms,
                    livingArea,
                    lotSize,
                    zpid,
                    county,
                    price,
                    afterRehabValue,
                    openingBid,
                    property_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    # Redirect to the admin page or another appropriate page
    user_role = session.get("user_role")
    if user_role == 2:
        return redirect(url_for("admin"))
    elif user_role == 1:
        return redirect(url_for("agent"))
    else:
        # Handle unexpected roles or if the user is not logged in
        return "Unauthorized", 401


@application.route("/delete/<int:id>", methods=["GET"])
def delete_address(id):
    delete_property(id)
    return redirect(url_for("admin"))


def get_photos(zpid):
    conn = http.client.HTTPSConnection("zillow56.p.rapidapi.com")
    headers = {
        "X-RapidAPI-Key": os.environ.get("X-RapidAPI-Key"),
        "X-RapidAPI-Host": os.environ.get("X-RapidAPI-Host"),
    }

    conn.request("GET", f"/photos?zpid={zpid}", headers=headers)
    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))

    # Check if 'photos' key exists and has at least one photo
    if "photos" in response_json and response_json["photos"]:
        # Access the first photo's 'mixedSources'
        mixed_sources = response_json["photos"][0].get("mixedSources", {})
        # Check if 'jpeg' key exists and has at least one JPEG source
        if "jpeg" in mixed_sources and mixed_sources["jpeg"]:
            # Access the 'url' of the first JPEG source
            first_photo_url = mixed_sources["jpeg"][0].get("url", None)
            return first_photo_url

    return None  # Return None if no photo URL is found

@application.route('/submit_bid/<int:property_id>', methods=['POST'])
def submit_bid(property_id):
    # Ensure the user is logged in
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in to submit a bid.'}), 403
    
    # Retrieve user details from session for the email
    user_id = session.get('user_id')
    username = session.get('user_username')
    first_name = session.get('first_name')
    last_name = session.get('last_name')
    email = session.get('user_email')
    phone = session.get('user_phone')


    property_address = get_address_by_id(property_id)
    
    if not property_address:
        return jsonify({'error': 'Property not found.'}), 404

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO bids (user_id, property_id, bid_progress)
            VALUES (%s, %s, 'Pending')
            """
            cursor.execute(sql, (user_id, property_id))
        conn.commit()



        send_bid_receipt_email_to_admin(phone, property_address, email, first_name, last_name, username)
        
    except Exception as e:
        # Log the error and return an appropriate error message
        print(f"Error submitting bid or sending email: {e}")
        return jsonify({'error': 'An error occurred while submitting the bid or sending emails.'}), 500
    finally:
        if conn:
            conn.close()

    # Bid was successfully submitted and emails sent
    return jsonify({'message': 'Your intent to bid was submitted successfully! The Bonaventura Team will reach out to you shortly.'}), 200

def get_address_by_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT addresses FROM all_properties WHERE id = %s", (property_id,))
            result = cursor.fetchone()
            if result:
                return result['addresses']  # Returns only the address string
            else:
                return None  # Property not found
    finally:
        conn.close()


@application.route("/admin/bids")
def admin_bids():
    # Fetch bids from the database
    bids = (
        get_all_bids_with_progress()
    )  # Ensure this function is implemented to fetch bids

    return render_template("admin_bids.html", bids=bids)


def get_all_bids_with_progress():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Join the bids table with the users table
            cursor.execute(
                """
                SELECT b.id, b.property_id, b.bid_time, b.bid_progress, 
                       u.username, u.email, u.phone
            FROM bids b
            INNER JOIN users u ON b.user_id = u.id
            """
            )
        return cursor.fetchall()
    finally:
        conn.close()


@application.route("/delete_bid/<int:bid_id>", methods=["GET", "POST"])
@requires_roles(2)  # Ensure only admins can access this route
def delete_bid(bid_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM bids WHERE id = %s", (bid_id,))
            conn.commit()
        flash("Bid deleted successfully!", "success")
    except Exception as e:
        application.logger.error(f"Error deleting bid: {e}")
        flash("An error occurred while deleting the bid.", "error")
    finally:
        if conn:
            conn.close()
        return redirect(url_for("admin_bids"))


@application.route("/update_bid_progress", methods=["POST"])
def update_bid_progress():
    bid_id = request.form["bid_id"]
    new_status = request.form["new_status"]

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE bids SET bid_progress = %s WHERE id = %s"
            cursor.execute(sql, (new_status, bid_id))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("admin_bids"))


@application.route("/my_bids")
def my_bids():
    if "user_id" not in session:
        return redirect(
            url_for("login_form")
        )  # Redirect to login if the user is not logged in

    user_id = session["user_id"]
    bids = get_bids_by_user_id(user_id)  # Fetch bids for the logged-in user

    # Add property details to each bid
    for bid in bids:
        property_id = bid["property_id"]
        property = get_property_by_id(property_id)
        bid["property_address"] = property["addresses"] if property else "Unknown"

    return render_template("subscriber_bids.html", bids=bids)


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


@application.route("/cancel_bid/<int:bid_id>", methods=["POST"])
def cancel_bid(bid_id):
    if "user_id" not in session:
        return redirect(
            url_for("login_form")
        )  # Redirect to login if the user is not logged in

    user_id = session["user_id"]

    # Check if the user has permission to cancel the bid
    if not can_user_cancel_bid(user_id, bid_id):
        flash("You do not have permission to cancel this bid.", "error")
        return redirect(url_for("subscriber"))  # Redirect back to the user's bids page

    try:
        # Cancel the bid in the database
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "DELETE FROM bids WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (bid_id, user_id))
        conn.commit()
        flash("Bid cancelled successfully.", "success")
    except Exception as e:
        # Log the error for debugging
        application.logger.error(f"Error cancelling bid: {e}")
        flash("An error occurred while cancelling the bid.", "error")
    finally:
        if conn:
            conn.close()

    return redirect(url_for("subscriber"))  # Redirect back to the user's bids page


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
    with open(file_path, "rb") as file:
        pdf_reader = PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text


def extract_auction_details(pdf_text):
    pattern = r"(DATE OF SALE: \d{1,2}/\d{1,2}/\d{2,4}|RESCHEDULED: \d{1,2}/\d{1,2}/\d{2,4})\s+Action:.*?\nTIME: (\d{1,2}:\d{2} (AM|PM)) Premises: (.*?) - (.*?)\n.*?FINAL JUDGMENT AS OF .*? - \$(\d{1,3}(?:,\d{3})*)"
    matches = re.findall(pattern, pdf_text, re.DOTALL)

    auction_details = []
    for date, time, am_pm, address_part1, address_part2, final_judgment in matches:
        cleaned_date = datetime.strptime(date.split(": ")[1], "%m/%d/%y").strftime(
            "%Y-%m-%d"
        )
        cleaned_time = f"{time} {am_pm}".strip()
        cleaned_address = f"{address_part1} - {address_part2}".strip()
        cleaned_final_judgment = int(
            final_judgment.replace(",", "")
        )  # Convert to integer

        auction_details.append(
            (cleaned_address, cleaned_date, cleaned_time, cleaned_final_judgment)
        )

    return auction_details


@application.template_filter("format_currency")
def format_currency(value):
    return "${:,.2f}".format(value) if value else "N/A"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_photo(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS_PHOTO
    )


@application.route("/upload_pdf", methods=["GET", "POST"])
def upload_pdf():
    if request.method == "POST":
        file = request.files["file"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            print(f"File saved at {file_path}")  # Debug print
            process_pdf(file_path)

            flash("File successfully uploaded and processed")
            return redirect(url_for("admin"))
    return render_template("upload_pdf.html")


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
                update_property(property_id, date_of_sale, time_of_sale, price)
                print(
                    f"Updating Address: {address}, Date: {date_of_sale}, Time: {time_of_sale}, Price: {price}"
                )
            else:
                insert_address(
                    address,
                    zpid,
                    details.get("bedrooms", None),
                    details.get("bathrooms", None),
                    details.get("livingArea", None),
                    details.get("lotSize", None),
                    details.get("county", None),
                    photo_url,
                    date_of_sale,
                    time_of_sale,
                    price,
                )
                print(
                    f"Inserting New Address: {address}, Date: {date_of_sale}, Time: {time_of_sale}, Price: {price}"
                )
        except Exception as e:
            print(f"Error processing address {address}: {e}")
            continue

    print("Processing of PDF completed.")


@application.route("/properties/<date>")
@requires_roles(0,1,2)
def properties_for_day(date):

    try:
        # Convert string date to datetime object
        selected_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return "Invalid date format", 400

    # Fetch properties and their most recent photo for the selected date
    properties = get_properties_for_date_with_photos(selected_date)
    user_role = session.get("user_role")

    today = datetime.today()
    current_date = today.strftime("%Y-%m-%d")

    selected_county = request.args.get("county", type=str)

    counties = get_unique_counties()

    if selected_county:
        properties = [
            prop for prop in properties if prop.get("county") == selected_county
        ]

    return render_template(
        "propertiesforday.html",
        properties=properties,
        selected_date=selected_date,
        user_role=user_role,
        selected_county=selected_county,
        counties=counties,
        current_date=current_date
    )


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
            cursor.execute(
                "SELECT * FROM all_properties WHERE dateOfSale = %s", (selected_date,)
            )
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


@application.route("/upload_photo/<int:property_id>", methods=["POST"])
def upload_photo(property_id):
    # Ensure the upload folder exists
    if not os.path.exists(application.config["IMAGES_FOLDER"]):
        os.makedirs(application.config["IMAGES_FOLDER"])

    if "photo" not in request.files:
        flash("No file part")
        return redirect(request.url)

    file = request.files["photo"]

    if file.filename == "":
        flash("No selected file")
        return redirect(request.url)

    if file and allowed_photo(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config["IMAGES_FOLDER"], filename)
            file.save(file_path)
            insert_photo(property_id, file_path)
            flash("Photo uploaded successfully!")
        except Exception as e:
            flash(f"An error occurred: {e}")
            # Log the error for debugging
            application.logger.error(f"Error uploading file: {e}")
            print("Error uploading")
            return redirect(request.url)

    return redirect(url_for("manage_photos", property_id=property_id))


def insert_photo(property_id, photo_url):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO property_photos (property_id, photo_url) VALUES (%s, %s)"
            cursor.execute(sql, (property_id, photo_url))
        conn.commit()
        print(
            f"Photo inserted: {photo_url} for property {property_id}"
        )  # Add this line
    finally:
        conn.close()


@application.route("/upload_interior_photo/<int:property_id>", methods=["POST"])
def upload_interior_photo(property_id):
    if "photo" not in request.files:
        flash("No photo part")
        return redirect(request.url)
    file = request.files["photo"]
    if file.filename == "":
        flash("No selected file")
        return redirect(request.url)
    if file and allowed_photo(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(application.config["IMAGES_FOLDER"], filename)
        file.save(file_path)
        # Here, insert a record in your database to associate the photo with the property_id
        insert_interior_photo(property_id, file_path)
        flash("Interior photo uploaded successfully!")
    return redirect(url_for("edit_address", id=property_id))


def insert_interior_photo(property_id, photo_url):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO interior_photos (property_id, photo_url) VALUES (%s, %s)"
            cursor.execute(sql, (property_id, photo_url))
        conn.commit()
    finally:
        conn.close()


@application.route("/manage_photos/<int:property_id>", methods=["GET", "POST"])
def manage_photos(property_id):
    if request.method == "POST":
        if "photo" not in request.files:
            flash("No file part")
            return redirect(request.url)

        file = request.files["photo"]
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config["IMAGES_FOLDER"], filename)
            file.save(file_path)

            insert_photo(property_id, file_path)
            flash("Photo uploaded successfully!")
            return redirect(url_for("manage_photos", property_id=property_id))

    photos = get_photos_by_property_id(property_id)
    print(f"Photos for property {property_id}: {photos}")  # Debug print

    return render_template("manage_photos.html", property_id=property_id, photos=photos)


@application.route("/delete_photo/<int:photo_id>", methods=["POST"])
def delete_photo(photo_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # SQL query to delete the photo with the given id
            query = "DELETE FROM property_photos WHERE id = %s"
            cursor.execute(query, (photo_id,))
        conn.commit()
        flash("Photo deleted successfully.", "success")
    except Exception as e:
        print(f"Error deleting photo with id {photo_id}: {e}")
        flash("Error deleting photo.", "error")
    finally:
        conn.close()
    # Redirect back to the manage_photos page or another appropriate page
    return redirect(url_for("admin"))


@application.route("/delete_interior_photo/<int:photo_id>", methods=["POST"])
def delete_interior_photo(photo_id):
    try:
        property_id = delete_interior_photo_from_db(
            photo_id
        )  # This now returns property_id
        if property_id:
            flash("Photo deleted successfully.")
            return redirect(
                url_for("edit_address", id=property_id)
            )  # Use returned property_id for redirection
        else:
            flash("An error occurred. Property ID not found.")
    except Exception as e:
        flash("An error occurred while deleting the photo.")
        application.logger.error(f"Error deleting interior photo {photo_id}: {e}")

    # Fallback redirection if property_id is not found or any other error occurs
    return redirect(url_for("admin"))  # Adjust as necessary


def delete_interior_photo_from_db(photo_id):
    conn = (
        get_db_connection()
    )  # Ensure you have a function or method to get your DB connection
    property_id = None
    try:
        with conn.cursor() as cursor:
            # First, retrieve the property_id before deletion
            cursor.execute(
                "SELECT property_id FROM interior_photos WHERE id = %s", (photo_id,)
            )
            property_id_row = cursor.fetchone()
            if property_id_row:
                property_id = property_id_row[0]

            # Then, delete the photo
            cursor.execute("DELETE FROM interior_photos WHERE id = %s", (photo_id,))
        conn.commit()
    finally:
        conn.close()
    return property_id


YOUR_DOMAIN = os.environ.get("YOUR_DOMAIN")

import logging
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_email_message(app_id, sender, to_addresses, subject, html_message):
    pinpoint_client = boto3.client("pinpoint", region_name="us-east-1")

    # Ensure to_addresses is a list of email addresses
    if not isinstance(to_addresses, list) or not all(isinstance(addr, str) for addr in to_addresses):
        raise ValueError("to_addresses must be a list of non-empty strings.")

    addresses_dict = {addr: {"ChannelType": "EMAIL"} for addr in to_addresses if addr}

    # Check if addresses_dict is not empty
    if not addresses_dict:
        raise ValueError("Addresses dictionary is empty. Check the to_addresses list.")

    try:
        response = pinpoint_client.send_messages(
            ApplicationId=app_id,
            MessageRequest={
                "Addresses": addresses_dict,
                "MessageConfiguration": {
                    "EmailMessage": {
                        "FromAddress": sender,
                        "SimpleEmail": {
                            "Subject": {"Charset": "UTF-8", "Data": subject},
                            "HtmlPart": {"Charset": "UTF-8", "Data": html_message},
                            "TextPart": {"Charset": "UTF-8", "Data": "Text version of the email content"},
                        },
                    }
                },
            },
        )
    except ClientError as e:
        logger.exception("Couldn't send email via Pinpoint: %s", e)
        return None
    else:
        return response["MessageResponse"]["Result"]


def send_bid_receipt_email_to_admin(phone, address, email, first_name, last_name, username):
    app_id = os.environ.get("pinpoint_app_id")
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    to_addresses = ["mikemeyers@bonaventurarealty.com"]
    subject = f"Notification of Bid on {address}"

    html_message = f"""
    <html>
        <head></head>
        <body>
            <p>{first_name} {last_name} placed bid on {address}.</p>
            <p>{first_name} {last_name}'s Email: {email}</p>
            <p>{first_name} {last_name}'s Phone: {phone}</p>
            <p>{first_name} {last_name}'s Username: {username}</p>
        </body>
    </html>
    """

    message_ids = send_email_message(
        app_id, sender, to_addresses, subject, html_message
    )
    return message_ids


if __name__ == "__main__":
    application.run(port=4242)
