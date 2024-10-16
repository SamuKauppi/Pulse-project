from machine import Pin, SoftI2C
import network
import socket
import urequests
import utime
import ujson

APIKEY = "pbZRUi49X48I56oL1Lq8y8NDjq6rPfzX3AQeNo3a"
CLIENT_ID = "3pjgjdmamlj759te85icf0lucv"
CLIENT_SECRET = "111fqsli1eo7mejcrlffbklvftcnfl4keoadrdv1o45vt9pndlef"
LOGIN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/login"
TOKEN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/oauth2/token"
REDIRECT_URI = "https://analysis.kubioscloud.com/v1/portal/login"
ANALYZE_URL = "https://analysis.kubioscloud.com/v2/analytics/analyze"
    
    
def send_post_request(url, data=None, headers=None, auth=None, json=None):
    response = urequests.post(url, data=data, headers=headers, auth=auth, json=json).json()
    return response
    

def get_access_token():

    response = send_post_request(TOKEN_URL,
                                 'grant_type=client_credentials&client_id={}'.format(CLIENT_ID),
                                 {'Content-Type':'application/x-www-form-urlencoded'},
                                 (CLIENT_ID, CLIENT_SECRET))
    return response['access_token']
    
    
def analyze_hrv(data, token):
    headers = {
        "Authorization": "Bearer {}".format(token),
        "X-Api-Key": APIKEY
    }
        
    data = {
        "type": "RRI",
        "data": data,
        "analysis": {
            "type": "readiness"
        }
    }  
    return send_post_request(ANALYZE_URL, None, headers, None, data)
