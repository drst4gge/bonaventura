import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime

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

    app_id = 'abccb22dc4414fe0b229357f51a1cdde'  
    sender = '"Bonaventura Realty" <info@bonaventurarealty.com>'
    to_addresses = ['dstagge@bonaventurarealty.com', 'cskowron1@gmail.com', 'cskowron21@gmail.com', 'mikemeyers@bonaventurarealty.com']
    subject = 'Your Daily Properties Update'
    
    # Generate the dynamic URL based on the current date
    current_date = datetime.now().strftime("%Y-%m-%d")
    properties_url = f"https://www.bonaventurarealty.com/properties/{current_date}"
    
    # Construct the HTML message with the dynamic URL
    html_message = f"""
    <html>
        Dear valued subscriber,<div><br></div>
        <div>Good morning! We hope this message finds you well and excited to explore new opportunities.&nbsp;</div>
        <div><br></div>
        <a style="text-decoration: none; font-style: italic;" href="{properties_url}"">Today's Exclusive Property Options</a>
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
        
