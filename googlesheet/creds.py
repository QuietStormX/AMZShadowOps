from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2 import service_account

import os


SCOPES = ['https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/spreadsheets']

def get_creds():
    """
    get creds for the Google services
    """
    creds = service_account.Credentials.from_service_account_file("./googlesheet/creds/credentials.json", scopes=SCOPES)
    return creds
