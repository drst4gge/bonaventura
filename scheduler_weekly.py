import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
load_dotenv()

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

from flask import current_app

def send_test_email():
    app_id = os.environ.get('pinpoint_app_id') 
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    to_addresses = ['dstagge@bonaventurarealty.com', 'cskowron1@gmail.com', 'cskowron21@gmail.com', 'mikemeyers@bonaventurarealty.com']
    subject = 'Your Weekly Properties Update'
    
    # Generate the dynamic URLs based on the next Monday to Friday dates
    base_url = "https://www.bonaventurarealty.com/properties/"
    html_message = '<html>Dear valued subscriber,<div><br></div><div>Good evening!&nbsp;</div><div><br></div>'
    
    for i in range(1, 6):  # Monday (1) to Friday (5)
        next_day_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        properties_url = f"{base_url}{next_day_date}"
        html_message += f'<a style="text-decoration: none; font-style: italic;" href="{properties_url}">Options for {next_day_date}</a><br>'
    
    html_message += """
        <div><br></div>
        <div>Should you have any questions or need further assistance, please do not hesitate to reach out. Our dedicated team of professionals is here to provide you with personalized support every step of the way.</div>
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
    
    # Send the email
    message_ids = send_email_message(app_id, sender, to_addresses, subject, html_message)

def main():
    send_test_email()

if __name__ == "__main__":
    main()
        
