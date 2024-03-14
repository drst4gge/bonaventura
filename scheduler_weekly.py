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
                            # If you have a text version of the message, add it here
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
    to_addresses = ['dstagge@bonaventurarealty.com']  # Shortened for brevity
    to_phone_numbers = ['+17652125159']  # Shortened for brevity

    user_first_names = get_user_first_names(to_addresses)

    base_url = "https://www.bonaventurarealty.com/properties/"

    for phone_number in to_phone_numbers:
        # Simplified SMS message without personalization
        sms_message = f"Good evening, \nYour weekly properties update is ready."
        for i in range(1, 6):  # Monday (1) to Friday (5)
            next_day_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            properties_url = f"{base_url}{next_day_date}"
            sms_message += f"\n{next_day_date}: {properties_url}"

        send_sms_message(app_id, sender_phone_number, [phone_number], sms_message)

    for email in to_addresses:
        user_first_name = user_first_names.get(email, "Valued Customer")
        html_message = f'<html>Dear {user_first_name},<div><br></div><div>Good evening!&nbsp;</div><div><br></div>'

        for i in range(1, 6):  # Monday (1) to Friday (5)
            next_day_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            properties_url = f"{base_url}{next_day_date}"
            html_message += f'<a style="text-decoration: none; font-style: italic;" href="{properties_url}">Options for {next_day_date}</a><br>'

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
    send_test_notifications()

if __name__ == "__main__":
    main()
        
