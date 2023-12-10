from flask import Flask, request, render_template, redirect, url_for
import pymysql
import http.client
import json

app = Flask(__name__)

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


@app.route('/')
def home():
    county_filter = request.args.get('county')
    properties = get_all_properties()
    detailed_properties = []
    counties = get_unique_counties()

    for prop in properties:
        id, address, bedrooms, bathrooms, livingArea, lotSize, price, taxAssessedValue, taxAssessedYear, county, photo_url = prop

    detailed_properties.append({
        'id': id,
        'address': address,
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'livingArea': livingArea,
        'lotSize': lotSize,
        'price': price,
        'taxAssessedValue': taxAssessedValue,
        'taxAssessedYear': taxAssessedYear,
        'county': county,
        'photo_url': photo_url
    })

    if county_filter:
        properties = [prop for prop in properties if prop.get('county') == county_filter]

    return render_template('index.html', properties=properties, counties=counties)

@app.route('/admin')
def admin():
    properties = get_all_properties()
    # Convert 'id' to integer if necessary
    for property in properties:
        property['id'] = int(property['id'])
    return render_template('admin.html', properties=properties)


@app.route('/property/<int:id>')
def property_details(id):
    property = get_property_by_id(id)

    if property:
        # Since the photo URL is already part of your property object, no need to fetch it again
        # Just pass the entire property object to the template
        return render_template('property_details.html', property=property)
    else:
        return 'Property not found', 404

@app.route('/login', methods=['GET'])
def login_form():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    # Here, you should fetch the user from the database and check the password
    # For now, this is a simplified version
    if username == 'admin' and password == 'password':
        return redirect(url_for('admin'))  # Redirect to the admin page
    else:
        return 'Invalid credentials', 401

@app.route('/add_address', methods=['GET'])
def add_address():
    return render_template('add_address.html')

@app.route('/submit_address', methods=['POST'])
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

@app.route('/edit/<int:id>', methods=['GET'])
def edit_address(id):
    property = get_property_by_id(id)
    if property:
        return render_template('edit_address.html', property=property)
    return 'Property not found', 404

@app.route('/update_address', methods=['POST'])
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

@app.route('/delete/<int:id>', methods=['GET'])
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

@app.route('/handle_bid/<int:id>', methods=['POST'])
def handle_bid(id):
    # Retrieve form data
    name = request.form['name']
    email = request.form['email']
    phone = request.form['phone']
    bid = request.form['bid']

    # Process the bid here (e.g., store in database, send notification, etc.)

    # Redirect or inform the user
    return redirect(url_for('property_details', id=id))


if __name__ == '__main__':
    app.run(debug=True)

