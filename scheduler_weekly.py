from flask import current_app
import logging
import boto3
import pymysql
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import os
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

def get_all_users_numbers_and_emails_and_names():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT DISTINCT phone, email, first_name FROM users")
            return cursor.fetchall()
    finally:
        conn.close()

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
    
def send_weekly_notifications():
    app_id = os.environ.get('pinpoint_app_id')
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    sender_phone_number = '+18885411353'
    
    # Fetch all users' phone numbers, emails, and names
    users_data = get_all_users_numbers_and_emails_and_names()

    base_url = "https://www.bonaventurarealty.com/properties/"
    for user in users_data:
        email = user['email']
        # Ensure phone numbers are correctly formatted
        phone_number = '+1' + user['phone'].lstrip('+1')
        user_first_name = user.get('first_name', "Valued Customer")
        
        # Determine the next Monday date to start the weekly update
        today = datetime.now()
        next_monday = today + timedelta((7 - today.weekday()) % 7 or 7)  # Calculate next Monday

        # Prepare and send SMS
        sms_message = f"Good evening {user_first_name}, \nYour weekly properties update is ready."
        for i in range(0, 5):  # Monday (0) to Friday (4)
            day_date = (next_monday + timedelta(days=i)).strftime("%Y-%m-%d")
            properties_url = f"{base_url}{day_date}"
            sms_message += f"\n{day_date}: {properties_url}"
        send_sms_message(app_id, sender_phone_number, [phone_number], sms_message)
        
        # Prepare and send Email
        html_message = f'<html>Dear {user_first_name},<div><br></div><div>Good evening!&nbsp;</div><div><br></div>'
        for i in range(0, 5):  # Monday (0) to Friday (4)
            day_date = (next_monday + timedelta(days=i)).strftime("%Y-%m-%d")
            properties_url = f"{base_url}{day_date}"
            html_message += f'<a style="text-decoration: none; font-style: italic;" href="{properties_url}">Options for {day_date}</a><br>'
        html_message += """
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
        send_email_message(app_id, sender, [email], "Your Weekly Properties Update", html_message)





def main():
    send_weekly_notifications()

if __name__ == "__main__":
    main()
