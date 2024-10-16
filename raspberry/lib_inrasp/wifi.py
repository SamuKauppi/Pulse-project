import network
import urequests
import utime

class WLAN:
    def __init__(self):
        self.wlan = None
    
    def connect(self):
        self.wlan = network.WLAN(network.STA_IF)
        #self.wlan = network.WLAN(network.AP_IF)
        self.wlan.active(True)
        self.wlan.connect('KMD657Group5', 'OIPSRA155')
        #self.wlan.connect('DNA-WIFI-5Ghz-692E', '80820257226')

        while self.wlan.isconnected() == False:
            print('Wifi connecting...')
            utime.sleep(1)    
        
    def post(self, url, data=None):
        if self.wlan.isconnected():
            urequests.post(url, json=data)
        else:
            print('Failed to send POST request. WLAN is not connected')