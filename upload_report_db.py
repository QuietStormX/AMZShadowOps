##########################################
# This file uploads the final_report.csv #
# to google bigquery database            #
##########################################


import pandas_gbq
import pandas as pd
import os
import sys
import math
import pandas as np
import time
from googlesheet2.creds import get_creds
from datetime import datetime

#file that is need to be uploaded
FILE_NAME = "final_report.csv"

#google project id
project_id = "reviewsdb"

#add credentials and project id to the library
pandas_gbq.context.credentials = get_creds()
pandas_gbq.context.project = "reviewsdb"

def upload_report_to_database():
    """
    uploads the FILE_NAME csv to the google big query DB
    """
    print("uploading report to database")


    if not os.path.exists(FILE_NAME):
        print(f"{FILE_NAME} is not present to upload the report to data base")
        return

    input_reviews = pd.read_csv(FILE_NAME)
    input_reviews['Date'] = input_reviews['TimeStamp_UTC'].apply(lambda x: datetime.strptime(x.split("__")[0],"%d-%m-%Y").strftime("%m-%d-%Y"))
    input_reviews['Time'] = input_reviews['TimeStamp_UTC'].apply(lambda x: x.split("__")[1])
    input_reviews['Captcha_Appeared'] = input_reviews['Captcha Appeared']
    input_reviews['Captcha_Resolved'] = input_reviews['Captcha Resolved']
    input_reviews.drop(['Captcha Resolved', 'Captcha Appeared'], axis=1,inplace=True)
    if len(input_reviews) < 1:
        print("No reviews are available in the input file.")
        return

    
    batch = 30000
    for i in range(math.ceil(len(input_reviews)/batch)):

        df = input_reviews[i*batch:(i+1)*batch]
        if len(df) > 0:
            pandas_gbq.to_gbq(df, "reviewsdb.reviews.reports", if_exists='append')
            pass
        time.sleep(10)

    print("report uploaded to database")