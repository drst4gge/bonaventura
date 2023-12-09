from flask import Flask, request, render_template, redirect, url_for
import pymysql, http.client, json

app = Flask(__name__)

# Database helper functions
def get_db_connection():
    return pymysql.connect(
        host="bonaventura-mysql.cponyf6gvfgg.us-east-1.rds.amazonaws.com",  
        user="admin",      
        password="Mylove707",
        db="properties",
        port=3306 
    )

def insert_address(address, zpid, bedrooms, bathrooms):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            insert_sql = """
            INSERT INTO all_properties (addresses, zpid, bedrooms, bathrooms) 
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (address, zpid, bedrooms, bathrooms))
        conn.commit()
    finally:
        conn.close()

def get_all_properties():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, addresses, zpid FROM all_properties")

            return cursor.fetchall()
    finally:
        conn.close()

def get_property_by_id(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, addresses, address_data FROM all_properties WHERE id = %s", (property_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def update_property(property_id, address, address_data):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            update_sql = "UPDATE all_properties SET addresses = %s, address_data = %s WHERE id = %s"
            cursor.execute(update_sql, (address, address_data, property_id))
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
    propertyTaxRate = response_json.get('propertyTaxRate', 'N/A')
    yearBuilt = response_json.get('yearBuilt', 'N/A')
    lastSoldPrice = response_json.get('lastSoldPrice', 'N/A')
    taxAssessedValue = response_json.get('taxAssessedValue', 'N/A')
    taxAssessedYear = response_json.get('taxAssessedYear', 'N/A')

    return {
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'livingArea': livingArea,
        'lotSize': lotSize,
        'propertyTaxRate': propertyTaxRate,
        'price': price,
        'yearBuilt': yearBuilt,
        'lastSoldPrice': lastSoldPrice,
        'taxAssessedValue': taxAssessedValue,
        'taxAssessedYear': taxAssessedYear


        # Add other details here
    }


@app.route('/')
def home():
    properties = get_all_properties()
    detailed_properties = []

    for property in properties:
        id, address, zpid = property
        property_details = get_property_details(zpid) if zpid else "Details not available"
        detailed_properties.append((id, address, property_details))

    return render_template('index.html', properties=detailed_properties)


# Route to display the form for adding a new address
@app.route('/add_address', methods=['GET'])
def add_address():
    return render_template('add_address.html')

@app.route('/submit_address', methods=['POST'])
def submit_address():
    address = request.form['address']

    zpid = get_zpid_from_address(address)
    if zpid:
        property_details = get_property_details(zpid)
        bedrooms = property_details.get('bedrooms')
        bathrooms = property_details.get('bathrooms')
    else:
        zpid, bedrooms, bathrooms = None, None, None

    # Save address and property details to the database
    insert_address(address, zpid, bedrooms, bathrooms)

    return redirect(url_for('home'))

# Route to display the edit address form
@app.route('/edit/<int:id>', methods=['GET'])
def edit_address(id):
    property = get_property_by_id(id)
    if property:
        return render_template('edit_address.html', property=property)
    return 'Property not found', 404

# Route to handle the submission of the edit address form
@app.route('/update_address', methods=['POST'])
def update_address():
    property_id = request.form['id']
    address = request.form['address']
    address_data = request.form['data']
    update_property(property_id, address, address_data)
    return redirect(url_for('home'))

# Route to handle deletion of an address
@app.route('/delete/<int:id>', methods=['GET'])
def delete_address(id):
    delete_property(id)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
