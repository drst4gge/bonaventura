from flask import current_app
import logging
import boto3
import os
import pymysql
from botocore.exceptions import ClientError
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Helper Functions
def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('database_host'),
        user=os.environ.get('database_user'),
        password=os.environ.get('database_password'),
        db=os.environ.get('database_db'),
        port=3306
    )

def get_user_first_names(email_list):
    conn = get_db_connection()
    first_names = {}
    try:
        with conn.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(email_list))
            sql = f"SELECT email, first_name FROM users WHERE email IN ({format_strings})"
            cursor.execute(sql, tuple(email_list))
            for row in cursor.fetchall():
                first_names[row[0]] = row[1]
    finally:
        conn.close()
    return first_names

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

def send_sms_message(app_id, sender_phone_number, to_phone_numbers, message):
    pinpoint_client = boto3.client('pinpoint', region_name='us-east-1')
    try:
        response = pinpoint_client.send_messages(
            ApplicationId=app_id,
            MessageRequest={
                "Addresses": {
                    phone_number: {"ChannelType": "SMS"} for phone_number in to_phone_numbers
                },
                "MessageConfiguration": {
                    "SMSMessage": {
                        "Body": message,
                        "MessageType": "TRANSACTIONAL",
                        "OriginationNumber": sender_phone_number
                    }
                }
            }
        )
    except ClientError as e:
        logger.exception("Couldn't send SMS via Pinpoint: %s", e)
        return None
    else:
        return response['MessageResponse']['Result']

def send_test_notifications():
    app_id = os.environ.get('pinpoint_app_id')
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    sender_phone_number = '+18885411353' 
    to_addresses = ['dstagge@bonaventurarealty.com', 'cskowron1@gmail.com', 'cskowron21@gmail.com', 'mikemeyers@bonaventurarealty.com']
    to_phone_numbers = ['+17652125159', '+12033565886', '+12033565611', '+16312605400']  

    # Fetch first names for all addresses
    user_first_names = get_user_first_names(to_addresses)

    # Iterate over each address to send personalized emails
    for email in to_addresses:
        user_first_name = user_first_names.get(email, "Valued Customer")

        # Generate the dynamic URL based on the current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        properties_url = f"https://www.bonaventurarealty.com/properties/{current_date}"
        
        # Construct the personalized HTML message
        html_message = f"""
        <html>
            Dear {user_first_name},<div><br></div>
            <div>Good morning!&nbsp;</div>
            <div><br></div>
            <a style="text-decoration: none; font-style: italic;" href="{properties_url}"">Properties for {current_date}</a>
            <div><br></div>
            <div>Should you have any questions, please do not hesitate to reach out. Our dedicated team of professionals is here to provide you with personalized support every step of the way.</div>
            <div><br></div>
            <div>Thank you for your continued trust in Bonaventura Realty. We look forward to helping you achieve your real estate goals.&nbsp;</div>
            <div><br></div>
            <div>Warm regards,</div>
            <div>Bonaventura Realty Team</div>
            <div><br></div>
            <div><br></div>
            <div><br></div>
        </html>
        """

        # Send the email individually
        send_email_message(app_id, sender, [email], "Your Daily Properties Update", html_message)
    
    # SMS content
    sms_message = f"Good morning {user_first_name}, \nThese are the properties scheduled for foreclosure auction today ({current_date}). \n{properties_url}"
    
    # Send the SMS to each phone number
    for phone_number in to_phone_numbers:
        send_sms_message(app_id, sender_phone_number, [phone_number], sms_message)

def main():
    send_test_notifications()

if __name__ == "__main__":
    main()
