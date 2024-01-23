import gspread
import pandas as pd
from apiclient.discovery import build
from apiclient.http import MediaFileUpload,MediaIoBaseDownload

import time
import json
import datetime 
from typing import List,Union
import os

from .creds import get_creds




CREDS = get_creds() #credentials for the google services
G_CLIENT = gspread.authorize(CREDS) #initiates the gspread client
folder = ""
date = datetime.datetime.now()


CRED_SHEET = "10diWoqVAOpBBy0Xi7PGuccEqOf0ObTQcpS6Iv-1oqCY" #credentials sheet id

credentials = []

def get_credentials_of_profiles():
    try:
        spread_sheet = G_CLIENT.open_by_key(CRED_SHEET)
    except:
        print(f"main working sheet not found: {id}",)
    
    try:
        sheet = spread_sheet.get_worksheet(0)
    except:
        print(f"sheet not found")
        return
    
    data = pd.DataFrame(sheet.get_all_records()).astype(str)
    data = data[['Buyer Profile','Email','Password']]
    data['ML Profile'] = data['Buyer Profile']
    data = data[['ML Profile','Email','Password']]
    data['Email'] = data["Email"].str.replace("\n","").str.strip()
    data['Password'] = data['Password'].apply(lambda x: x.split("--")[-1] if len(x.split("--")) > 1 else x)
    data['Password'] = data['Password'].str.replace("AMAZON","").str.strip()
    data.to_csv("Credentials.csv")




def update_sheet(data,id):
    """
    updates the first tab of the google sheet regonized by ID.\n
    params:\n
    data: panda dataframe of the data\n
    id: id of the sheet\n
    """
    try:
        spread_sheet = G_CLIENT.open_by_key(id)
    except:
        print(f"main working sheet not found: {id}",)
    
    try:
        sheet = spread_sheet.get_worksheet(0)
    except:
        print(f"sheet not found")
        return

    try:
        json_data = data.fillna('').astype(str)
        sheet.clear()
        sheet.update([json_data.columns.values.tolist()] + json_data.values.tolist())

    except Exception as e:
        print("")
        print(e)

def create_google_spreadsheet(title: str, parent_folder_ids: list=None, share_domains: list=None):
    """Create a new spreadsheet and open gspread object for it.
    .. note ::
        Created spreadsheet is not instantly visible in your Drive search and you need to access it by direct link.
    :param title: Spreadsheet title
    :param parent_folder_ids: A list of strings of parent folder ids (if any).
    :param share_domains: List of Google Apps domain whose members get full access rights to the created sheet. Very handy, otherwise the file is visible only to the service worker itself. Example:: ``["redinnovation.com"]``.
    """

    credentials = CREDS

    drive_api = build('drive', 'v3', credentials=credentials)

    body = {
        'name': title,
        'mimeType': 'application/vnd.google-apps.spreadsheet',
    }

    
    body["parents"] = [parent_folder_ids]

    req = drive_api.files().create(body=body)
    new_sheet = req.execute()

    # Get id of fresh sheet
    spread_id = new_sheet["id"]

    # Grant permissions
    if share_domains:
        for domain in share_domains:

            # https://developers.google.com/drive/v3/web/manage-sharing#roles
            # https://developers.google.com/drive/v3/reference/permissions#resource-representations
            domain_permission = {
                'type': 'domain',
                'role': 'writer',
                'domain': domain,
                # Magic almost undocumented variable which makes files appear in your Google Drive
                'allowFileDiscovery': True,
            }

            req = drive_api.permissions().create(
                fileId=spread_id,
                body=domain_permission,
                fields="id"
            )

            req.execute()

    return spread_id
        
def create_folder(parentId:str,date:str) ->str:
    """Create a new folder inside parent folder named as the date. and returns the folder id\n
    :param parentId: id of the parent folder\n
    :param date:date or any name as a string format.\n
    """

    credentials = CREDS

    drive_api = build('drive', 'v3', credentials=credentials)

    file_metadata = {
            'name': date,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parentId]
        }
    res = drive_api.files().create(body=file_metadata,fields='id').execute()
    return res['id']


def upload_file(file_name,folder_id):
    """
    uploads file to google drive\n
    params:\n
    file_name: path of the file\n
    folder_id: id of the folder where it needs to be uploaded.\n
    """
    credentials = CREDS
    drive_api = build('drive', 'v3', credentials=credentials)
    file_metadata = {
    'name': file_name,
    'mimeType': '*/*',
    "parents": [folder_id]
    }
    media = MediaFileUpload(file_name,
                            mimetype='*/*',
                            resumable=True)
    file = drive_api.files().create(body=file_metadata, media_body=media, fields='id').execute()
    try:
        if os.path.exists(file_name):
            os.remove(file_name)
    except:
        pass

def search_folders(topFolderId:str,date:str) ->str:
    """searches for a folder inisde the given parent. if not found will create one and return its id\n
    :param parentId: id of the parent folder\n
    :param date:date or any name as a string format.\n
    """
    credentials = CREDS

    drive_api = build('drive', 'v3', credentials=credentials)

    items = []
    pageToken = ""
    while pageToken is not None:
        response = drive_api.files().list(q="'" + topFolderId + "' in parents", pageSize=1000, pageToken=pageToken, fields="nextPageToken, files(id, name)").execute()
        items.extend(response.get('files', []))
        pageToken = response.get('nextPageToken')

    folder = list(filter(lambda x: x['name'] == date,items))

    if len(folder) > 0:
        return folder[0]['id']

    else:
        return create_folder(topFolderId,date) 
    

def append_to_sheet(id:str,data,header:bool):
    """appends data to the first tab of a sheet with the given id for fmain and fmainx\n
    params:
    id: id of the sheet\n
    data:dataframe of the data.\n
    header:add the header in the sheet or not.\n
    """
    try:
        spread_sheet = G_CLIENT.open_by_key(id)
    except:
        print(f"main working sheet not found: {id}",)
    
    try:
        sheet = spread_sheet.get_worksheet(0)
    except:
        print(f"sheet not found")
        return

    try:
        if len(data) > 0:
            data = pd.DataFrame(data)
            try:
                data = data[["Total_URLs","URL_Counter","Profile_Name","Product_ID","Page_Number","Total_Reviews","Review_Counter","Review_ID","Review_Country","Review_URL","Unique_Identifier","Report_Button_Clicked","Captcha Appeared","Captcha Resolved","Submit_Button_Clicked","TimeStamp_UTC"]]
            except:
                pass
            json_data = data.fillna('').astype(str)
            if header:
                sheet.append_rows([json_data.columns.values.tolist()] + json_data.values.tolist())
            else:
                sheet.append_rows(json_data.values.tolist())
    except Exception as e:
        print(e)
        pass

def append_to_sheet2(id,data,header:bool):
    """appends data to the first tab of a sheet with the given id with different format\n
    params:
    id: id of the sheet\n
    data:dataframe of the data.\n
    header:add the header in the sheet or not.\n
    """
    try:
        spread_sheet = G_CLIENT.open_by_key(id)
    except:
        print(f"main working sheet not found: {id}",)
    
    try:
        sheet = spread_sheet.get_worksheet(0)
    except:
        print(f"sheet not found")
        return

    try:
        if len(data) > 0:
            data = pd.DataFrame(data)
            try:
                data = data[["Total_URLs","Profile_Name","Product_ID","Review_ID","Review_Country","Review_URL","Unique_Identifier","Report_Button_Clicked","Captcha Appeared","Captcha Resolved","Submit_Button_Clicked","TimeStamp_UTC"]]
            except:
                pass
            json_data = data.fillna('').astype(str)
            if header:
                sheet.append_rows([json_data.columns.values.tolist()] + json_data.values.tolist())
            else:
                sheet.append_rows(json_data.values.tolist())
    except Exception as e:
        print(e)
        pass

def add_new_reviews(machine_name:str,data:pd.DataFrame):
    """
    adds reviews to the "new reviews" sheet in the tab named according to the machine_name\n
    params:\n
    machine_name: name of the machine\n
    data:dataframe of the data.\n
    """

    try:
        spread_sheet = G_CLIENT.open_by_key("1rGEkkNS82fiqN42Qaozj4vIlN1FOlot_QaVBLiPcOew")
    except:
        print(f"main working sheet not found: {id}",)

    try:
        sheet = spread_sheet.worksheet(machine_name)
    except:
        sheet = spread_sheet.add_worksheet(title=machine_name,cols=50, rows=1000)

    sheet.clear()
    data = data.drop_duplicates(subset=['Review_ID']).fillna("").astype(str)
    sheet.update([data.columns.values.tolist()] + data.values.tolist())

def add_reviews() -> List:
    """
    gets all the reviews ids we have in the googlesheet
    """
    try:
        spread_sheet = G_CLIENT.open_by_key("1S1t-kIgbGoVGjTeDb2i1-_1nEmJtEs_ZGqzSdEiz5Qo")
    except:
        print(f"main working sheet not found: {id}",)

    try:
        sheet = spread_sheet.worksheet("All Available Reviews")
    except:
        print("no sheet found")
        raise Exception
    
    data = pd.DataFrame(sheet.get_all_records())
    return data['IDs'].unique()

def update_dashboard(id:str,status:str,reviews_reported:int,total_urls:int,current_url:int,machine:str):
    """
    updates the tracking dashboard.
    params:\n
    id: name of the machine\n
    status:status of the machine.\n
    reviews_reported: how many reviews are reported so far \n
    total_urls: how many urls were in the input file\n
    current_url: the current url number being ran\n
    machine: name of the machine \n
    """
    try:
        spread_sheet = G_CLIENT.open_by_key(id)
    except:
        print(f"main working sheet not found: {id}",)
    
    try:
        sheet = spread_sheet.get_worksheet(0)
    except:
        print(f"sheet not found")
        return

    try:
        print(sheet.get_all_values())
        data = pd.DataFrame(sheet.get_all_records()).to_dict('records')
        print("ok")
        index = None
        for i,d in enumerate(data):
            print(d['Machine'],machine)
            if d['Machine'] == machine:
                index = i
                break
        print(index)
        if index is not None:
            if total_urls == 0:
                total_urls = data[i]['Total URLs']
            if current_url == 0:
                total_urls = data[i]['URL']
            sheet.update(f'B{index+2}:F{index+2}', [[status,reviews_reported,total_urls,current_url,datetime.datetime.utcnow().strftime("%d-%m-%Y %H:%M:%S")]])
        else:
            sheet.append_row([machine,status,reviews_reported,total_urls,current_url,datetime.datetime.utcnow().strftime("%d-%m-%Y %H:%M:%S")])
    except Exception as e:
        print(e)
        pass


