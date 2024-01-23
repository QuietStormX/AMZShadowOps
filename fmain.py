##########################################
# This file run the report abuse script  #
# that report each review one time using #
# multilogin6                            #
##########################################



import csv
import glob
import json
import os
import random
import time
import traceback
from datetime import datetime
from typing import Tuple, Union
from dotenv import load_dotenv

import pandas as pd
import pyautogui
import requests
from amazoncaptcha import AmazonCaptcha
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.common import (ElementClickInterceptedException,
                             NoSuchElementException, NoSuchWindowException,
                             StaleElementReferenceException, TimeoutException,
                             WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

from googlesheet.core import (add_new_reviews, add_reviews,
                              create_google_spreadsheet, search_folders,
                              update_dashboard, update_sheet,upload_file)
from login import main as autologin
from upload_report_db import upload_report_to_database


load_dotenv()

DAS_ID = "1LA8NpPfFgk3rWv4CHcMsjTaY4lRDSeSMR_niZ8_kDK0" #tracking dashboard gsheet id
MACHINE = os.getenv('MACHINE',"Test") #machine name
ALL_URLS = [] #it will store all the urls the input have


def serialize(record):
    subset = {
        "datetime": record["time"].strftime('%Y-%m-%d %H:%M:%S'),
        "level": record["level"].name,
        "message": record["message"],
        "line": record["line"],
    }
    return json.dumps(subset)


def formatter(record):
    record["extra"]["serialized"] = serialize(record)
    return "{extra[serialized]}\n"


logger.add(
    f"logs/fmain_{datetime.now().strftime('%d_%m_%Y')}.json",
    format=formatter
)


def get_profiles() -> dict:
    df = pd.read_csv('profiles.csv')
    profiles_list = df.to_dict('records')
    profiles_dict = {}
    for profile in profiles_list: #goes through each profile in the list of profiles
        profiles_dict[profile['Profile Name'].strip()] = profile['Profile ID'] # stores relavent information in the dictionary

    return profiles_dict # returns the dictionary



def read_from_input_file(input_file_path:str) -> tuple[list,list]:
    """
    Reads input file:\n
    params:\n
    input_file_path: path to the input file
    """
    if os.path.exists(input_file_path): # check if input.csv file is exists. 
        df = pd.read_csv(input_file_path) # reads the input.csv
        urls = df['Url'].unique() # we make sure the urls are unique gotten form input.csv
        profiles = df['Profile'].unique() # we make sure the profiles are unique gotten form input.csv

        return urls, profiles # return the list of profiles and urls

    return [],[] #returns empty list if the input file doesn't exists


def start_profile(port:int, profile_id:str, profile_name:str, max_retries:int = 5) -> str:
    """
    starts a multlogin profile\n
    params:\n
    port: multilogin API port \n
    profile_id: uuid of the profile \n
    profile_name: name of the profile \n
    max_retrires: number of retries to do if the request fails \n
    """
    mla_url = f"http://127.0.0.1:{port}/api/v1/profile/start?automation=true&profileId=" + profile_id # multilogin API endpoint to spin up a profile 

    for retry_counter in range(max_retries): # retires loop if the request fails
        try:
            response = requests.get(mla_url) # makes request to the API

            response_json = response.json() # converts the response to the json

            if response.status_code != 500: # if the request is not 500 we accept the response
                return response_json["value"] # the remote url for the browser is returned

        except requests.exceptions.Timeout:
            logger.warning(f"Profile Name = {profile_name}. Request Timeout.")

        except requests.exceptions.ConnectionError:
            logger.warning(f"Profile Name = {profile_name}. Please Make Sure MultiLogin API Is Running. Failed To Make Request To The API.")

        except requests.exceptions:
            logger.error(f"Profile Name = {profile_name}. Request Failed Due To.")
            print(traceback.format_exc())

        except Exception as e:
            logger.error(f"Profile Name = {profile_name}. Generic Exception Raised.")
            logger.exception(e)
            print(traceback.format_exc())

        if retry_counter >= max_retries - 1:
            logger.info(f"Profile Name = {profile_name}. Profile Not Opened.")
            return

        logger.warning(f"Profile Name = {profile_name}. Unable To Connect. Retrying...")

        time.sleep(10) # if the requests fail we wait for 10 seconds and try again.


def stop_profile(port:int, profile_id:str) -> None:
    """
    Stops a multilogin profile\n
    params:\n
    port: port the multilogin api\n
    profiles_id:uuid of the multilogin profile\n

    """
    mla_url = f"http://127.0.0.1:{port}/api/v1/profile/stop?profileId={profile_id}" #multilogin API endpoint that stops a profile

    try:
        requests.get(mla_url) #makes request to the url mentioned above
    except Exception:
        pass


def focused_click(driver, element) -> None:
    """
    clicks on a element. if the browser is hidden it will first bring it forth and then click on the element \n
    pramas:\n
    driver:selenium driver object \n
    element:element that needs to be clicked on \n
    """
    while True:
        try:
            while driver.title not in pyautogui.getActiveWindowTitle(): #if the active window title is not same as the driver window title
                pyautogui.getWindowsWithTitle(driver.title)[0].activate()  # we find the window and bring it forth
        except Exception:
            pass

        try:
            webdriver.ActionChains(driver).move_to_element(element).click(element).perform() # using webdriver action chain first we move to the element and the click on it
            break
        except ElementClickInterceptedException: # if the element is hidden error is raised and we try again.
            logger.error("Element Click Intercepted.")
            pass 


def check_if_page_exists(driver):
    """
    checks if the page is 404 or not\n
    pramas:\n
    driver:selenium driver object \n
    """
    page_title = driver.title # store the page title

    if page_title == "Amazon.com Page Not Found" or page_title == "Page Not Found": # if the driver title meets any of the two strings it will return False
        return False #it means the page is 404

    return True #it means page is not 404


def check_if_page_contains_captcha(driver):
    """
    checks if the page has captcha or not\n
    pramas:\n
    driver:selenium driver object \n
    """
    return "Try different image" in driver.page_source # if the text exist it will mean there is captcha and return true else false


def wait_until_page_is_loaded(driver, profile_name:str): 
    """
    checks if the page is loaded or not\n
    pramas:\n
    driver: selenium driver object \n
    profile_name: name of the current profile that is open \n
    """
    try:
        WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.ID, "nav-logo"))) # check if the #nav-logo is present in the page. it will mean the page is loaded

    except TimeoutException:
        logger.info("page not loaded fully refreshing the page")
        driver.refresh() # reloads the page in case the page was not loaded fully

        try:
            WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.ID, "nav-logo"))) # check if the #nav-logo is present in the page. it will mean the page is loaded

        except TimeoutException:
            while True:
                if "This site can’t be reached" in driver.page_source: # checks if the there is server error
                    logger.info("This site can’t be reached. Refreshing browser")
                    time.sleep(15) #sleep of 15 seconds
                    driver.refresh()  # reload the page
                    time.sleep(5) # sleep for 5 seconds
                else:
                    break # break the loop if the there is not server error

            if "HTTP ERROR 407" in driver.page_source: # checks for the 407 error in the page. that is caused due to the proxt authentication
                # we noticed that this issue gets resolved if we load google and go back to amazon
                current_url = driver.current_url # stores the current amazon url for reference  
                time.sleep(2) #sleep of 2 seconds
                goto_page(driver, "https://www.google.com/") #loads google on the page
                time.sleep(2) #sleep of 2 seconds
                goto_page(driver, current_url) # then goes back to amazon
                time.sleep(2) #sleep of 2 seconds

                if "HTTP ERROR 407" in driver.page_source: # further checks if the 407 error exists
                    logger.error("407 error") #print that the page has 407 error
                    return False #return false as the page is not loaded

            page_exists = check_if_page_exists(driver) # checks if the page is 404 or not

            if not page_exists: # if the page doesn't exists return None 
                return 

            WebDriverWait(driver, 5).until(ec.presence_of_element_located((By.ID, "nav-logo"))) #to confirm again the page is loaded


def goto_page(driver, url:str, short_time_delay:float=0.1, long_time_delay:float=10, perform_ready_state_check:bool=True) -> None:
    """
    loads a given url\n
    pramas:\n
    driver: selenium driver object \n
    url: name of the current profile that is open \n
    short_time_delay: this delay is for checking if the page is in ready state or not through JS \n
    long_time_delay: this delay is for waiting after any error happens while loading the url \n
    perform_ready_state_check: a bool value to either check the ready state of the page or not \n
    """
    while True: #loop to make sure the url is loaded
        try:
            driver.get(url) #loads the urls
            break
        except WebDriverException: #genric error 
            time.sleep(long_time_delay) #sleep for defined time if any error occured while loading the URL
    t1 = time.perf_counter() # start time for a stopwatch
    while perform_ready_state_check: # check for the ready state of the page
        
        time.sleep(short_time_delay) # waits for the defined time

        page_state = driver.execute_script("return document.readyState;") #js function to check if the page is in ready state or not

        if page_state == "complete": #complete means that the page is in ready state.
            break #ends the loop if the page is ready

        t2 = time.perf_counter() #checkpoint for the stopwatch
        if t2 - t1 >= 90: #if stopwatch is running for more than 90 seconds
            time.sleep(10) #sleep for 10 seconds
            goto_page(driver, url) # retry to got to the url

    if "www.google" in url: # if the url was for google
        if "HTTP ERROR 407" in driver.page_source: # if the error was 407
            goto_page(driver,"https://www.amazon.com") # go to amazon.com it seems to fix it

    elif "www.amazon" in url: # if the url was for amazon
        if "HTTP ERROR 407" in driver.page_source: # if the error was 407
            goto_page(driver, "https://www.google.com") # go to google.com it seems to fix it


def scroll_element_into_view(driver, element) -> None:
    """
    scrolls to the given element\n
    pramas:\n
    driver: selenium driver object \n
    element: element to which we needs to scroll
    """
    driver.execute_script('arguments[0].scrollIntoView();',element) #JS function to scroll the element in to the view port
    


def is_profile_logged_in(driver) -> bool:
    """
    Checks if the amazon account is logged in\n
    pramas:\n
    driver: selenium driver object \n
    """
    #check for the ata-nav-ref="nav_youraccount_btn" element if it exists it mean the account is logged in.
    #if logged in will return true else false
    return bool(driver.find_elements(By.XPATH, './/a[@data-nav-ref="nav_youraccount_btn"]')) 


def solve_captcha(driver, max_retries = 5) -> bool:
    """
    tries to solve captcha\n
    pramas:\n
    driver: selenium driver object \n
    max_retries: number of retries we need to do \n
    """

    for retry_counter in range(max_retries): #loop to manage the retries
        logger.info(f"Trying to Solve Captcha. Retry Counter {retry_counter + 1}")

        try:
            href = driver.find_element(By.XPATH, ".//img[contains(@src, 'captcha')]").get_attribute('src') #gets the captcha image source from the page

            captcha = AmazonCaptcha.fromlink(href) # provides the image url to the amazonCaptcha library

            solution = captcha.solve() #uses the amazonCaptcha library to extract text from the image

            logger.info(f"Captcha Solution - {solution}")

            driver.find_element(By.CSS_SELECTOR, 'input#captchacharacters').send_keys(solution) #find the text box to enter the captcha text

            time.sleep(1) #sleep for 1 seconds

            element = driver.find_element(By.CSS_SELECTOR, 'button.a-button-text') #find the submit button to submit the captcha form
 
            focused_click(driver, element) #click on the submit button

            time.sleep(1) #sleep for 1 seconds

            if check_if_page_contains_captcha(driver): #confirm if the captcha was indeed solved
                time.sleep(5)  #sleep for 5 seconds and the loop will continue

            else:
                logger.info("Captcha Solved")
                return True #captcha was solved so we return ture

        except Exception: #in case any error happends
            print(traceback.format_exc()) #we print the traceback of the error

    logger.warning("Captcha Not Solved") #if we reach to this point that will mean captcha was not solved

    return False #return false as captcha was not solved


def wait_until_review_loading_animation_is_hidden(driver) -> bool:
    """
    tries to solve captcha\n
    pramas:\n
    driver: selenium driver object \n
    max_retries: number of retries we need to do \n
    """
    while True: #loop to make sure the loading animation is hidden before we continue 
        try:
            driver.find_element(By.XPATH, './/div[@class="a-section cr-list-loading reviews-loading aok-hidden"]') #if thje animation is hidden we will find the element
            return #exit the loop and funciton

        except NoSuchElementException: #if the element is not found meaing the loading is still there
            time.sleep(0.1) #wait for 0.1 seconds


def get_page_number_from_url(url)-> int:
    """
    retreives page number from the given url\n
    pramas: \n
    url: url from which we need to extract the page number \n
    """
    if "pageNumber=" not in url: # if the page number is not in the url return -1
        return -1

    page_number = int(url.split("pageNumber=")[1].split("&")[0]) #finds the page number

    return page_number #return the page number


def refresh_page_and_let_exception_be_raised_if_necessary(driver) -> None:
    """
    checks for the next button on the reviews page if not found raises exception\n
    pramas: \n
    driver: selenium web driver \n
    """
    logger.info("page number mismatch while paginating refreshing browser")
    driver.refresh() #reloads the page

    try:
        WebDriverWait(driver, 30).until(ec.presence_of_element_located((By.XPATH, './/li[@class="a-last"]'))) #checks for the next page button

    except TimeoutException as te: #if button not found
        logger.exception(te)
        logger.error("Exception Is Being Raised Because Next Page Button Cannot Be Located Even After Refreshing The Browser And Waiting For 30 Seconds.")
        raise Exception


def click_next_page_button(driver, previous_url_page_number:int):
    """
    clicks on the next page button on the reviews page
    pramas: \n
    driver: selenium web driver \n
    previous_url_page_number: previous page number \n
    """
    url = driver.current_url #current url of the tab

    next_url = url.replace(f"pageNumber={previous_url_page_number}",f"pageNumber={previous_url_page_number + 1}") #replace the pageNumber with new one by adding 1 to it.

    # why we are not clicking on the next page page and going directly to next page?
    # it is because at one point amazon disabled the next page button after 10 pages due to which script was not able to reach to the more reviews
    # but they didn't limit the reviews in the backend when we go directly to pagenumber greater then 10 we could get more reviews
    goto_page(driver, next_url) #goto the next page

    page_exists = check_if_page_exists(driver) #check if the page is 404 or not

    if not page_exists: #if its 404
        return False 

    current_url_page_number = get_page_number_from_url(driver.current_url) #get the pagenumber from the currently loaded url

    if previous_url_page_number == current_url_page_number: #check if the new page is same as the old one
        refresh_page_and_let_exception_be_raised_if_necessary(driver) #checks for the next button on the reviews page if not found raises exception

    elif previous_url_page_number + 1 == current_url_page_number: #make sure that the new page was indeed loaded
        return True
    
    return False #return false meaning we couldn't goto next page.

def ensure_popup_gets_closed(driver, main_window_handle):
    """
    make sures that the report popup was closed
    pramas: \n
    driver: selenium web driver \n
    main_window_handle: main window handle where the reviews page is loaded \n
    """
    try:
        while True: #loop to make sure the popup is closed
            driver.close()

    except NoSuchWindowException: #no popup was found
        pass

    driver.switch_to.window(main_window_handle) #we switch to the main handle here the reviews page is loaded

    while driver.current_window_handle != main_window_handle: #we check to make sure the correct handle is selected if not we do it agian
        driver.switch_to.window(main_window_handle)


def ensure_popup_open_when_report_is_clicked(driver, report_button, time_delay:float = 0.1) -> Tuple[str,bool]:
    """
    make sures that the report popup gets open when clicked on the report button
    pramas: \n
    driver: selenium web driver \n
    report_button: selenium element object for the report button \n
    time_delay: wait after clicking on the report button \n
    """
    for _ in range(5): #loop for retries if error occurs
        focused_click(driver, report_button) #clicks on the report button
        time.sleep(time_delay) #sleeps for the defined time

        if len(driver.window_handles) == 2: #checks if the number of handles is 2 meaning popup was opened
            return "normal" #will return normal meaning we will report through old method where the popups opens
        
        try:
            WebDriverWait(driver, 40).until(ec.presence_of_element_located((By.CSS_SELECTOR,".a-modal-scroller.a-declarative"))) #checks for the new method where models opens in page
            if driver.find_element(By.CSS_SELECTOR,".a-modal-scroller.a-declarative"): #checks for the new method where models opens in page
                return "new" #return "new" meaining we report it through the new method after amazon update
        except:
            pass
        
    return False #meaning we failed to open the report popup or model after trying 5 times


def check_if_popup_is_a_report_popup(driver) -> bool:
    """
    check the current handle if it is indeed report window
    pramas: \n
    driver: selenium web driver \n
    """
    popup_title = driver.title #get title of the window

    #there is same text in spanish as one of the profiles was in spanish
    if popup_title == "Amazon.com:Report" or popup_title == "amazon.com:Reportar": # if any of the text exists it means that the popup is for the report action 
        return True

    return False


def get_popup_language(driver) -> str:
    """
    check the language of the report window
    pramas: \n
    driver: selenium web driver \n
    """
    popup_title = driver.title #get title of the window

    if popup_title == "Amazon.com:Report":  #if this text matches it will mean the profile is in english
        logger.info("Language is English")
        return "English"

    if popup_title == "amazon.com:Reportar": #if this text matches it will mean the profile is in spanish
        logger.info("Language is Spanish")
        return "Spanish"


def new_is_sign_in_popup(driver):
    """
    check for sign-in element in the report modal "new".
    pramas: \n
    driver: selenium web driver \n
    """

    heading = driver.find_elements(By.CSS_SELECTOR, ".a-popover h1") # find the element to identify if there is sign in element in the modal
    if len(heading)>0: #if the sign in heading is found
        heading = heading[0].text.strip() #strip the text to remove any leading and trailing spaces
    else: #not found
        heading = ""  

    return driver.title == "Amazon Sign-In" or heading == "Sign in" # if any of the text exists it means that the modal have sign in element


def is_sign_in_popup(driver):
    """
    check for sign-in element in the report popup "normal".
    pramas: \n
    driver: selenium web driver \n
    """
    heading = driver.find_element(By.TAG_NAME, "h1").text.strip() # strip the text to remove any leading and trailing spaces

    return driver.title == "Amazon Sign-In" or heading == "Sign in" # if any of the text exists it means that the popup have sign in element


def report_through_new_method(driver)-> Union[str,None,bool]:
    """
    reports a review through the amazon new method where modal appears inpage instead of popup outside the window.
    pramas: \n
    driver: selenium web driver \n
    """

    tt1 = time.perf_counter()
    while True:
        try:
            #sometimes the page is not loaded fully like css or js. the click on report button loads a new page
            #so this condtion checks if the report modal on same page or not
            if "product-reviews" not in driver.current_url:  
                return "except"
            
            time.sleep(2)

            #with brightdata sometimes funds were in negative when in middle of reporting that would cause the show of message because 
            #of that this condition was added to check if the options and buttons are present.
            #incase the message appears we close the modal and return False to indicate this error
            checkboxes = []
            for i in range(3):
                if "Sorry, content is not available" in driver.page_source:
                    logger.warning("Sorry, content is not available" )
                    close_btn= driver.find_element(By.CSS_SELECTOR,'button[data-action="a-popover-close"]')
                    focused_click(driver,close_btn)
                    
                    while True:
                        try:
                            driver.find_element(By.CSS_SELECTOR,".a-modal-scroller.a-declarative")
                        except:
                            break

                    return False
                
                #this code block choices a random selection from the given option and clicks on it
                checkboxes = driver.find_elements(By.CSS_SELECTOR,
                                                ".a-modal-scroller.a-declarative .a-fixed-left-grid-inner")

                logger.info(f"checkboxes - {len(checkboxes)}")
                if not checkboxes:
                    time.sleep(5)
                    continue
                break

            #if checkboxes are not found after 3 retries we continue to next review to be reported.
            if not checkboxes:
                return "continue"

            check = random.choice(checkboxes)
            element = check.find_element(By.CSS_SELECTOR,'.a-checkbox')
            focused_click(driver,element)
            logger.info(f"checkbox selected - [{check.text}]")

            #this code block after selection will click on submit button
            submit_btn = driver.find_element(By.CSS_SELECTOR,".a-modal-scroller.a-declarative .a-button-primary")
            focused_click(driver,submit_btn)
            logger.info("submit button clicked")

            #we initiate a stopwatch to count time. sometimes the proxies are slow and it takes time to load the message where it indicates the 
            #report was sucessfully reported.
            t1 = time.perf_counter() 
            while True:
                #we check for the messages where if the report was sucussfully submitted or not
                if "Thanks for your report" in driver.page_source or "Gracias por tu informe" in driver.page_source or "Sorry, content is not available" in driver.page_source :
                    logger.info('"Thanks for your report"  - appeared')
                    break
                else:
                    #we check for signin elements if the submit button trigered a sign in option for the account
                    #if did return the message "not signed in"
                    sign_in_popup = new_is_sign_in_popup(driver)
                    if sign_in_popup:
                        logger.info("not signed in")
                        return "not signed in"
                #end for stopwatch 
                #if the timer goes above 2 mins we close the modal and indicate a error with returning False
                t2 = time.perf_counter()
                if (t2-t1) >= 120:
                    close_btn= driver.find_element(By.CSS_SELECTOR,'button[data-action="a-popover-close"]')
                    focused_click(driver,close_btn)
                    logger.info('click close button')
                    return False
            
            #at this point all went well the report was submitted successfully and we close the modal
            close_btn= driver.find_element(By.CSS_SELECTOR,'button[data-action="a-popover-close"]')
            focused_click(driver,close_btn)
            logger.info("closed button clicked")
            
            #we confirm here if the modal was indeed closed or not
            while True:
                try:
                    driver.find_element(By.CSS_SELECTOR,".a-modal-scroller.a-declarative")
                except:
                    break
            
            #we escape from the loop here
            break
            
        except Exception as e:
            #this timmer checks for 10 mins if the errors keep happening for 10 mins it means something is really wrong and we need to
            #restart the script.
            tt2 = time.perf_counter()
            if(tt2 - tt1 >= 600):
                return "except" 
            print(e)


def handle_popup_operations(driver, review_tag, main_window_handle, profile_name:str, review_url:str, output_data:dict):
    """
    handles the operations form clicking on the report button in the review. that will either open a in page modal
    or a new window with option to report a review. this will report the review according to the condition
    pramas: \n
    driver: selenium web driver \n
    review_tag: review element from where we need to find the report button \n
    main_window_handle: main page window handle \n
    profile_name: name of the profile currently open \n
    review_url: url of the review we are about to report \n
    output_data: dictionary that contains report generation data \n
    """

    #we find the report button for the review we are going to report.
    report_button = review_tag.find_element(By.XPATH, './/a[@class="a-size-base a-link-normal a-color-secondary report-abuse-link a-text-normal"]')


    #A loop to make sure if we face error we can retry it
    while True:

        #get the status info of the report button being click if it is a inpage modal or new window popup
        status = ensure_popup_open_when_report_is_clicked(driver, report_button)
        logger.info(f"status - {status}")
        #in case nothing happens we raise a exception that will restart the script
        if not status:
            time.sleep(30)
            raise Exception
        
        #this indicts if the in page model was opened
        if status == "new":
            logger.info("procced with new method")
            #we register that the report button was clicked.
            output_data["Report_Button_Clicked"] = True

            #here we try to complete the report process
            reported = report_through_new_method(driver)
            logger.info(f"reported - {reported}")

            if reported == 'continue':
                output_data["Submit_Button_Clicked"] = False
                break 

            #an error occured that can be solved by retrying the report process
            if reported == False:
                continue

            #while reporting a sign in option appeared we return false to indicate this error
            if reported == 'not signed in':
                logger.warning('not signed in')
                return False
            
            #a non solvable error occured can be most likely solved by restarting the script. mainly can be related to proxy or profile related issue.
            elif reported == 'except':
                raise Exception
            
            #if we reach here if will mean that the report process was successful and we register it in our end report.
            #and we complete the function.
            output_data["Submit_Button_Clicked"] = True
            break 
        
        #from here the report process for the popup window begins.
        #here it is indicated that the report button was sucessfully clicked and we register it in our end report.
        output_data["Report_Button_Clicked"] = True

        #we select the popup window handle to continue the report process.
        popup_window_handle = [window_handle for window_handle in driver.window_handles if window_handle != main_window_handle][0]
        driver.switch_to.window(popup_window_handle)

        #we check if the captcha appeared or not
        if check_if_page_contains_captcha(driver):

            #we captcha did appear we register it in our end report.
            output_data["Captcha Appeared"] = True

            logger.info(f"Captcha Appeared. Profile Name: {profile_name}. Review URL: {review_url}")

            #we try to solve the captcha here.
            if solve_captcha(driver):
                #we captcha was solved we register it in our end report.
                output_data["Captcha Resolved"] = True

            #we the captcha was not solved
            else:
                #we register it in our end report.
                output_data["Captcha Resolved"] = False
                logger.warning(f"Captcha Not Solved. Profile Name: {profile_name}. Review URL: {review_url}")

                #close the popup and retry.
                ensure_popup_gets_closed(driver, main_window_handle)
                continue
        
        #we check here if the popup is indeed for the reporting process
        popup_check = check_if_popup_is_a_report_popup(driver)

        #if the pop up is not for the report it can be the page in the popup was not
        #loaded sucessfully and we faced some errors.
        if not popup_check:
            while True:
                #sometime proxies don't perform well or are slow we get this error in the page
                #it is solved by waiting for sometime and reloading the page.
                if "This site can’t be reached" in driver.page_source:
                    logger.warning("This site can’t be reached. refreshing browser")
                    time.sleep(15)
                    driver.refresh()
                    time.sleep(5)
                else:
                    break
            #sometime proxies authentication error appears
            #we close the popup and restart the script. it mostly solves the issue.    
            if "HTTP ERROR 407" in driver.page_source:
                ensure_popup_gets_closed(driver, main_window_handle)
                logger.warning("HTTP ERROR 407 Occurred In Popup")
                raise Exception

            #at this point none of the errors identified were present it a new erorr.
            #we close the popup and try again.
            ensure_popup_gets_closed(driver, main_window_handle)
            continue

        #we wait for the submit button to appear
        try:
            WebDriverWait(driver, 30).until(ec.presence_of_element_located((By.XPATH, './/a[@id="a-autoid-0-announce"]')))

        except TimeoutException:
            #we submit button doesn't appear we retry. closing the popup
            print(traceback.format_exc())
            ensure_popup_gets_closed(driver, main_window_handle)
            continue

        attempt = 0
        try:
            #we here try to click on the submit button.
            while True:
                attempt += 1
                submit_button = driver.find_element(By.XPATH, './/a[@id="a-autoid-0-announce"]')
                focused_click(driver, submit_button)

        except NoSuchElementException:
            pass

        logger.info(f'submit_button clicked - {attempt} times')
        #here it is indicated that the submit button was clicked and we register it in our end report.
        output_data["Submit_Button_Clicked"] = True

        #make sure that after clicking on the submit button are still on the same page.  
        popup_check = check_if_popup_is_a_report_popup(driver)

        #if the page changed it will because we got a signin window. we return false to deal with this error
        #if not we close the popup and try again
        if not popup_check:
            sign_in_popup = is_sign_in_popup(driver)

            ensure_popup_gets_closed(driver, main_window_handle)

            if sign_in_popup:
                return False

            continue
        
        #here we determine the language of the report window to match the success message 
        #to make sure the report was sucessfully submitted.
        popup_language = get_popup_language(driver)

        if popup_language == "English":
            WebDriverWait(driver, 30).until(ec.presence_of_element_located((By.XPATH, './/h1[contains(text(), "Thanks for your report")]')))
            logger.info("Thanks pop-up appeared")

        elif popup_language == "Spanish":
            WebDriverWait(driver, 30).until(ec.presence_of_element_located((By.XPATH, './/h1[contains(text(), "Gracias por tu informe")]')))
            logger.info("Thanks pop-up appeared")
        time.sleep(0.5)
        
        #we close the popup winodw
        ensure_popup_gets_closed(driver, main_window_handle)

        #at this point the report process was a success and we exit the function.
        break


def write_to_output_file(output_data:dict, output_file_path:str):
    """
    will write the end report info to the final_report.csv\n
    params:\n
    output_data: data that needs to be written.\n
    output_file_path: path for the output file.
    """
    logger.info(f"save data into the file = {output_file_path}")
    #check if the file exists or not
    file_exists = os.path.exists(output_file_path)

    #add the time when the review was reported
    output_data["TimeStamp_UTC"] = datetime.utcnow().strftime("%d-%m-%Y__%H:%M:%S")

    with open(output_file_path, mode = "a", newline = "") as output_file:
        writer = csv.DictWriter(output_file, fieldnames = output_data.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(output_data)


def read_from_output_file(output_file_path:str)->tuple[set,int,str,int,int]:
    """
    it will read from the output file to indetify the point from where the script was
    interrupted or stopped in case we need to continue.
    params:\n
    output_file_path: path for the output file.
    """
    unique_identifier_set = set() #gather all the unique reviews that were reported
    url_counter_resume_value = None #which url we have reported last
    profile_name_resume_value = None #which profile was being used at that time.
    page_number_resume_value = None #which page number we were at.
    review_counter_resume_value = None #which review we were at.

    #check if the file exists or not.if not that means we never reported a review.
    if os.path.exists(output_file_path):
        with open(output_file_path) as input_file:
            reader = csv.DictReader(input_file)
            #this block goes through each line of the csv file and save the details need to 
            #continue the script. 
            for row in reader:
                unique_identifier_set.add(row["Unique_Identifier"])
                url_counter_resume_value = int(row["URL_Counter"])
                profile_name_resume_value = row["Profile_Name"]
                page_number_resume_value = row["Page_Number"]
                review_counter_resume_value = int(row["Review_Counter"])

                total_reviews = int(row["Total_Reviews"])
                #in case the script was stopped when all reviews were reported or 100 reviews were reported we don't need to 
                #load that url again or the profile.
                if review_counter_resume_value >= total_reviews or review_counter_resume_value >= 100:
                    url_counter_resume_value += 1
                    page_number_resume_value = None
                    review_counter_resume_value = None

    return unique_identifier_set, url_counter_resume_value, profile_name_resume_value, page_number_resume_value, review_counter_resume_value


def get_total_reviews(driver) -> int:
    """
    get total number of reviews a product have.\n
    params:\n
    driver: selenium driver.
    """
    total_reviews_string = driver.find_element(By.XPATH, './/div[@data-hook="cr-filter-info-review-rating-count"]').text

    try:
        total_reviews = int(total_reviews_string.strip().split(" total ratings, ")[-1].split(" with review")[0].replace(",", "").strip())

    except ValueError:
        try:
            total_reviews = int(total_reviews_string.strip().split(", ")[-1].split(" ")[0].replace(",", "").strip())

        except ValueError:
            total_reviews = int(total_reviews_string.strip().replace("global reviews","").strip())

    return total_reviews


def wait_until_captcha_is_resolved(driver, profile_name:str)->None:
    """
    finds the captcha in the page and if exists try to solve it.
    params:\n
    driver: selenium driver.\n
    profile_name: name of the current profile.\n
    """

    #checks if the captcha is present in the page
    while check_if_page_contains_captcha(driver):
        logger.info(f"Captcha Appeared. Profile Name: {profile_name}")

        #solves the captcha
        if solve_captcha(driver):
            logger.info(f"Captcha Solved. Profile Name: {profile_name}")

        else:
            logger.warning(f"Captcha Not Solved. Profile Name: {profile_name}")


def wait_until_profile_is_logged_in(driver, profile_name)->bool:
    """
    checks if the profile is logged in or not and tries to log a profile in the amazon.
    params:\n
    driver: selenium driver.\n
    profile_name: name of the current profile.\n
    """
    #checks if the profile is logged in or not
    while not is_profile_logged_in(driver):
        try:
            url = driver.current_url
            # tries to log the profile in
            if autologin(driver, profile_name):
                # if logged goes back to the original url to continue the script.
                logger.info(f"profile [{profile_name}] signed in!")
                goto_page(driver, url)
                return True
            # was not logged in sucessfully. we return false.
            logger.error(f"profile [{profile_name}] NOT signed in!")
            return False
        except:
            # an error occured while logging a profile in and we return false.
            logger.error(f"profile [{profile_name}] NOT signed in!")
            return False


def perform_captcha_loaded_logged_in_checks(driver, profile_name:str)->Union[str,bool,None]:
    """
    A sequence of intruction to check for captacha and if the profile is logged in or not and check for 404\n
    params:\n
    driver: selenium driver.\n
    profile_name: name of the current profile.\n
    """
    #indentify if captcha is present or not and solve it
    #it is given if the captcha is to appear it will always appear first before getting to
    #the main page content.
    wait_until_captcha_is_resolved(driver, profile_name)

    #after solving captcha we check if the page was loaded fully or not.
    if wait_until_page_is_loaded(driver, profile_name) == False:
        return False

    #here we check for 404
    page_exists = check_if_page_exists(driver)

    #page doesn't exist
    if not page_exists:
        logger.info(f"page not exist - {driver.current_url}")
        return "404"

    #check if the profile is logged in or not and try to log in.
    if wait_until_profile_is_logged_in(driver, profile_name) == False:
        #if not logged in return false.
        return False


# def refresh_browser_to_clear_ram(driver, page_number:int)->None:
#     """
#     refreshes the page after 10 pages are loaded.\n
#     params:\n
#     driver: selenium driver.\n
#     page_number: current page number.\n
#     """
#     if page_number % 20 == 0:
#         logger.info("refreshing browser")
#         driver.refresh()


def handle_redirected_urls(driver, url_counter:int, profile_name:str, url:int, redirected_urls_file_path:str = "Redirected_URLs.csv"):
    """
    creates a record of url that were redirects\n
    params:\n
    driver: selenium driver.\n
    url_counter: current url number\n
    profile_name: name of the profile currently opened.\n
    url: url that caused the redirect.\n
    redirected_urls_file_path: path to the record file.\n
    """
    file_exists = os.path.exists(redirected_urls_file_path)

    with open(redirected_urls_file_path, mode = "a", newline = "") as output_file:
        writer = csv.DictWriter(output_file, fieldnames = ["URL_Counter", "Profile_Name", "Original_URL", "Redirected_URL"])

        if not file_exists:
            writer.writeheader()

        writer.writerow({"URL_Counter": url_counter, "Profile_Name": profile_name, "Original_URL": url, "Redirected_URL": driver.current_url})


def extract_country_name(top_level_domains:dict, review_country_and_date:str)->str:
    """
    get the name of the country that review was submitted from the tagline of the review\n
    params:\n
    top_level_domains: dictionary of all amazon domains\n
    review_country_and_date: tag line of the review that contains the country\n
    """
    review_country = None

    #loop through each domain to identify which contry it matches with and get the domain.
    for country in top_level_domains:
        if country in review_country_and_date:
            review_country = country
            break
    
    #if the country doesn't mahctes any return the whole text 
    if review_country is None:
        return review_country_and_date

    return review_country


def check_if_page_is_a_sign_in_page(driver)->bool:
    """
    checks if the page loaded is signin page or not\n
    params:\n
    driver: selenium driver.\n
    """
    return driver.title == "Amazon Sign-In"


def get_new_url(url:str):
    """
    This function is ran if the url is 404 or there are less then 2 reviews in the page.
    it will select the next url and log the old url as done.\n
    params:\n
    url: current url \n
    """
    logger.info('getting new url......')
    if os.path.exists("done.csv"):
        pd.DataFrame([{"url":url}]).to_csv("done.csv",mode='a',header=False)
    else:
        pd.DataFrame([{"url":url}]).to_csv("done.csv")
    try:
        url = ALL_URLS[ALL_URLS.index(url)+1]
        logger.info(f"new url - {url}")
        return url
    except:
        return False


def start_reporting(driver, profile_name:str, url:str, output_file_path:str, unique_identifier_set:set, total_urls:int, url_counter:int, top_level_domains:dict, review_counter:int,all_reviews:list, start_session_time)->Union[None,bool]:
    """
    starts the reporting process for the current url and profile\n
    pramas:\n
    driver: selenium driver object\n
    profile_name: name of the current profile opened\n
    url:url to report reviews on\n
    output_file_path: path of the output file where the progress of the script will be written\n
    unique_identifier_set: set of unique reviews ids that are reported\n
    total_urls: total urls the input have\n
    url_counter: number of the current url\n
    top_level_domains: all domains of the amazon\n
    review_counter: reviews that are reported for the current url\n
    all_reviews: ids of all the reviews we have in the database\n
    """
    while True:
        logger.info(f"starting profile for - {profile_name}")
        #gets the main window handle
        main_window_handle = driver.current_window_handle

        current_time = time.perf_counter()
        session_time = current_time - start_session_time
        if session_time > 160:
            logger.warning(f"current session time - {session_time} sec., profile {profile_name}")
            return False
        
        #get total number of review reported
        last_total = len(read_from_result_file("final_report.csv"))

        #loads the url
        goto_page(driver, url)

        time.sleep(5)
        
        #check if the page is 404 or not
        page_exists = check_if_page_exists(driver)
        
        #if 404 then load a new url and continue the loop
        if not page_exists:
            url = get_new_url(url)
            logger.info(f"for profile {profile_name}, getting new url - {url}")
            if url:
                continue
            else:
                break
        
        #checks if the page is a sign in page and if the profile is logged into the amazon or not.
        #if we fail to signin page we load a new url and continue the loop
        if check_if_page_is_a_sign_in_page(driver):
            logger.info(f"{profile_name}, not signed in, trying to login")
            if wait_until_profile_is_logged_in(driver, profile_name) == False:
                return False
        
        #check for captcha for the page, if the page is loaded or not and if the profile if logged in or not
        #if not try to log in
        #if any of the checks fail we return false and load a new profile and continue
        signin_status = perform_captcha_loaded_logged_in_checks(driver, profile_name)
        if signin_status == False:
            return False
        
        #if 404 then load a new url and continue the loop
        if signin_status == "404":
            url = get_new_url(url)
            if url:
                continue
            else:
                break
        
        #check if the page is 404 or not
        page_exists = check_if_page_exists(driver)
        
        #if 404 then load a new url and continue the loop
        if not page_exists:
            logger.info(f"for profile {profile_name}, page not exist, getting new url")
            url = get_new_url(url)
            if url:
                continue
            else:
                break
        
        #get the product id from the page
        product_id = driver.find_element(By.XPATH, './/link[@rel="canonical"]').get_attribute("href").split("/")[-1]

        #get total number of reviews the product have
        total_reviews = get_total_reviews(driver)

        #if the reviews are less then 2 then load a new url and continue the loop
        if total_reviews <= 2:
            logger.info(f"for profile {profile_name},"
                        f" and url - {driver.current_url}, there is less that 2 review, getting new url")
            url = get_new_url(url)
            if url:
                continue
            else:
                break
        

        #varaible to check if the next page button is active or not
        is_next_page_button_interactive = True

        while is_next_page_button_interactive:

            current_time = time.perf_counter()
            session_time = current_time - start_session_time
            if session_time > 160:
                logger.warning(f"current session time - {session_time} sec., profile {profile_name}")
                return False

            #gets the page number from the url
            page_number = get_page_number_from_url(driver.current_url)
            logger.info(f"page number - {page_number}")
            
            #if the page number is -1 this means that the pageNumber parameter in the url doesn't exist
            #and it was redirected and register the url
            if page_number == -1:
                handle_redirected_urls(driver, url_counter, profile_name, url)
                return

            #checks if the page number is multiple of 10 or not to reload the page
            
            #check for captcha for the page, if the page is loaded or not and if the profile if logged in or not
            #if not try to log in
            #if any of the checks fail we return false and load a new profile and continue
            signin_status = perform_captcha_loaded_logged_in_checks(driver, profile_name)
            if signin_status == False:
                return False
            
            #if 404 then load a new url and continue the loop
            if signin_status == "404":
                logger.info(f"profile - {profile_name}, got 404, getting new url")
                url = get_new_url(url)
                if url:
                    continue
                else:
                    break
        
            #get all the reviews present on the current page
            review_tags = driver.find_elements(By.XPATH, './/div[@data-hook="review"]')
            logger.info(f"found tags - {len(review_tags)}")

            #if no tags even the number of reviews is more than 0
            #something is wrong and change the profile
            if not review_tags and total_reviews > 0:
                return False

            #make sure that the review we are above to report is visible and present.
            while True:
                try:
                    for review_tag in review_tags:
                        review_tag.is_enabled()
                        review_tag.is_displayed()

                    break

                except StaleElementReferenceException:
                    logger.info("review tags are not visible refreshing browser")
                    driver.refresh()
                    time.sleep(5)

            #get total number of reviews
            total_reviews = get_total_reviews(driver)

            #collect the new reviews from the page and save to new_reviews.csv
            collect_info(driver,top_level_domains,unique_identifier_set,product_id,all_reviews)

            #to keep track of when to upload the tracking process on the tracking sheet
            old_count = review_counter
            
            #loop through each review and report
            for review_tag in review_tags:
                    
                scroll_element_into_view(driver, review_tag)

                #collect the id of the review
                review_id = review_tag.get_attribute("id")

                #collect country and date when the review was posted
                review_country_and_date = review_tag.find_element(By.XPATH, './/span[@data-hook="review-date"]').text.strip()

                review_country = extract_country_name(top_level_domains, review_country_and_date)

                if "United States" in review_country or "Estados Unidos" in review_country:
                    review_url = review_tag.find_element(By.XPATH, './/a[@data-hook="review-title"]').get_attribute("href").split("ref=")[0]

                #if the review is posted other than the US we don't get the url from the page for the review
                #we try to make our own
                elif review_country in top_level_domains:
                    review_url = f"{top_level_domains[review_country]}/gp/customer-reviews/{review_id}/"

                else:
                    review_url = ""

                unique_identifier = f"{review_id}"

                review_counter += 1

                #if the review is already reported we don't report it again
                if unique_identifier in unique_identifier_set:
                    logger.info(f"skipped - {unique_identifier}, already present in unique_identifier_set")
                    continue


                logger.info(f"Profile Name: {profile_name} | Total URLs: {total_urls} | URL Counter: {url_counter}")
                logger.info(f"Page Number: {page_number} | Total Reviews: {total_reviews} | Review Counter: {review_counter}")
                logger.info("#" * 100)

                #add revoew to the set to make sure we don't report it again
                unique_identifier_set.add(unique_identifier)

                #create data form inital report we are about to do for the review
                output_data = dict()

                output_data["Total_URLs"] = total_urls
                output_data["URL_Counter"] = url_counter
                output_data["Profile_Name"] = profile_name
                output_data["Product_ID"] = product_id
                output_data["Page_Number"] = page_number
                output_data["Total_Reviews"] = total_reviews
                output_data["Review_Counter"] = review_counter
                output_data["Review_ID"] = review_id
                output_data["Review_Country"] = review_country
                output_data["Review_URL"] = review_url
                output_data["Unique_Identifier"] = unique_identifier
                output_data["Report_Button_Clicked"] = False
                output_data["Captcha Appeared"] = False
                output_data["Captcha Resolved"] = False
                output_data["Submit_Button_Clicked"] = False
                output_data['machine'] = MACHINE
                
                #here we start to press the report button for the review and follow the process
                status = handle_popup_operations(driver, review_tag, main_window_handle, profile_name, review_url, output_data)

                #this means that the sign in page appeared while reporting the review and we then sign out the profile
                #and try to signin it back next time and in and resume reporting.
                if status == False:
                    sign_out_url = "https://www.amazon.com/gp/flex/sign-out.html?path=%2Fgp%2Fyourstore%2Fhome&signIn=1&useRedirectOnSuccess=1&action=sign-out&ref_=nav_AccountFlyout_signout"
                    goto_page(driver, sign_out_url)
                    time.sleep(2)
                    return False

                #writes the report to the output file
                write_to_output_file(output_data, output_file_path)

            #here we update the tracking dashboard with how many urls are done and how many reviews are reported.
            if old_count <= review_counter:
                last_total += (review_counter - old_count)
                old_count = review_counter
                update_dashboard(DAS_ID,"Working",last_total,total_urls,url_counter,MACHINE)

            #as amazon do not show more then 100 reviews for a product we end the loop here
            if review_counter >= 100 or review_counter >= total_reviews:
                break
            
            #checks if the next button is active and load the next page url
            is_next_page_button_interactive = click_next_page_button(driver, page_number)
        
        #ends the reporting for the current url and profile.
        break
        

def collect_info(driver,top_level_domains:dict,unique_identifier_set:set,product_id:str,all_reviews:list)->None:
    """
    collects new reviews from the page that are already not in our databse and save them to new_reviews.csv.
    this file will uploaded at the end of the script.\n
    params:\n
    driver: selenium driver.\n
    top_level_domains: dictionary of all amazon domains\n
    prodcut_id: current product asin\n
    all_reviews: ids of reviews we have in the database\n
    """

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    review_tags = soup.select('div[data-hook="review"]')

    #loops through all the reviews on the page
    for review_tag in review_tags:

        review_id = review_tag["id"]

        #if the reviews already exists in the database so we skip it.
        if review_id in all_reviews:
            continue
        
        #gets the date review was posted and the country text.
        review_country_and_date = review_tag.select_one('[data-hook="review-date"]').get_text().strip()

        #we extract date from the text
        review_date = review_country_and_date.split("on")[-1].strip()

        #we extract country from the text
        review_country = extract_country_name(top_level_domains, review_country_and_date)

        #this part extracts the title and create a url of the of the reviews. the structure is different for the reviews posted outside
        #US
        review_title = ""
        if "United States" in review_country or "Estados Unidos" in review_country:
            review_url = review_tag.select_one('[data-hook="review-title"]')
            review_title = review_url.get_text().split("out of 5 stars")[-1].strip()
            review_url = review_url['href'].split("ref=")[0]

        elif review_country in top_level_domains:
            review_url = f"{top_level_domains[review_country]}/gp/customer-reviews/{review_id}/"
            review_title = review_tag.select_one('[data-hook="review-title"]').get_text().strip()

        else:
            review_url = ""


        #gets the badge if the review is verified or not
        verified = review_tag.select('[data-hook="avp-badge"]')
        if len(verified) > 0:
            verified = verified[0].get_text().strip()
        else:
            verified = ""

        #gets the star rating of the review
        rating = review_tag.select('[data-hook="review-star-rating"]')
        if len(rating) > 0:
            rating = rating[0]["class"][2].replace("a-star-","").strip()
        elif len(review_tag.select('[data-hook="cmps-review-star-rating"]')) > 0:
            rating = review_tag.select('[data-hook="cmps-review-star-rating"]')[0]["class"][2].replace("a-star-","").strip()
        else:
            rating = ""

        #we get the name of the buyer who submitted the review
        author_name = review_tag.select('.a-profile-name')
        if len(author_name) > 0:
            author_name = author_name[0].get_text().strip()
        else:
            author_name=""  

        #we get the link and id of the buyer who submitted the review. for buyer from country other then US have
        #no link and id
        author_link = review_tag.select("a.a-profile")
        if len(author_link) > 0:
            author_link = author_link[0]["href"]
        else:
            author_link=""

        author_id = ""
        if len(author_link) > 0:
            author_id = author_link.split(".")[-1] 

        #gets the number of helpful votes the review have
        helpful = review_tag.select('[data-hook="helpful-vote-statement"]')
        if len(helpful) > 0:
            if "person" in helpful[0].get_text():
                helpful = 1
            else:
                helpful = helpful[0].get_text().split("people")[0].strip()
        else:
            helpful=0

        #stores all the data collected into the dictionary
        output_data = dict() 
        try:
            output_data["Product_ID"] = product_id
            output_data["Review_ID"] = review_id
            output_data["Review_Country"] = review_country
            output_data["Review_URL"] = review_url
            output_data['verified'] = verified
            output_data['author_name'] = author_name
            output_data['author_id'] = author_id
            output_data['helpful'] = helpful
            output_data['brand'] = soup.select_one("#cr-arp-byline > a").get_text()
            output_data['review_posted_date'] = review_date
            output_data['rating'] = rating
            output_data['author_link'] = author_link
            output_data['review_header'] = review_title
            output_data['review_text'] = review_tag.select_one('[data-hook="review-body"]').get_text().strip()

            file_exists = os.path.exists("new_reviews.csv")
            if file_exists:
                df = pd.read_csv("new_reviews.csv")
                df = df.to_dict("records")
            else:
                df = []
            df.append(output_data)
            pd.DataFrame(df).to_csv("new_reviews.csv",index=False)
        except:
            pass


def close_proifle_by_click() -> None:
    """
    closes the profile using the multilogin extension. it is believed it helps in storing the info of 
    the profile correctly.
    """
    try:
        #we get all the images they are in ordered form. and with multiple them settings
        image_path1 = ['images/extension_white.PNG','images/extension_black.png']
        image_path2 = ['images/ML_extension_white.PNG','images/ML_extension_black.png']
        image_path3 = 'images/second.png'

        #this process first click on the chrome extension button
        found_1=False
        for img in image_path1:
            img_location = pyautogui.locateOnScreen(img,confidence=0.8)
            if img_location:
                image_location_point = pyautogui.center(img_location)
                x, y = image_location_point
                pyautogui.click(x, y)
                found_1 = True
                break

        #this process finds the multilogin extension and clicks on it
        if found_1:        
            time.sleep(2)
            found_1=False
            for img in image_path2:
                img_location = pyautogui.locateOnScreen(img,confidence=0.8)
                if img_location:
                    image_location_point = pyautogui.center(img_location)
                    x, y = image_location_point
                    pyautogui.click(x, y)
                    found_1 = True

        #this process finds the "save and close" button on the extension and clicks on it.
        if found_1:        
            time.sleep(2)
            img_location = pyautogui.locateOnScreen(image_path3,confidence=0.8)
            image_location_point = pyautogui.center(img_location)
            x, y = image_location_point
            pyautogui.click(x, y)

    except Exception as e:
        print(e)
        logger.error("couldn't close")
        logger.exception(e)


def main(done_profile:list,all_reviews:list)->bool:
    """
    main entry point to start the report abuse operation.\n
    params:\n
    done_profiles: list of the profiles that were used before\n
    all_reviews: list of all reviews id we have in the database
    """
    port = 35111 #port number of the selenium API

    input_file_path = "input.csv" #input file for the script that contains the profiles and urls

    output_file_path = "final_report.csv" #output file were the script progress is written

    signout_file = "Profile_not_signed_in.csv" #output file were the script progress is written

    top_level_domains_file_path = "Top_Level_Domains.json" #all the amazon domains file

    if not os.path.exists(input_file_path):
        logger.warning(f"Input File Does Not Exists - [{input_file_path}]")
        return False

    with open(top_level_domains_file_path, "r", encoding="utf8") as json_file:
        top_level_domains = json.load(json_file)

    #reads from the output file if exists and if it does we find the point where script was stopped.
    unique_identifier_set, url_counter_resume_value, profile_name_resume_value, _, _ = read_from_output_file(output_file_path)

    #gets all profiles from the multilogin
    profiles = get_profiles()

    #if something went wrong while getting profiles from multilogin we close the script.
    if profiles is None:
        return False

    if not profiles:
        logger.error("No Profiles Available Inside MultiLogin")
        return False

    
    #get the urls and profiles from the input file.
    urls , profiles_input = read_from_input_file(input_file_path)

    if len(urls) < 1:
        logger.warning("Input File Is Empty")
        return False

    #indicates if we need to resume the script or not.
    read_page_number_and_review_counter_from_file = os.path.exists(output_file_path)
    
    #we filter any url that is not from amazon.
    urls = list(filter(lambda x: "amazon.com" in x,urls))
    total_urls = len(urls)

    #save all the urls from the input globally
    global ALL_URLS
    ALL_URLS = urls

    #here we start looping through each url present in the input file
    for url_counter, url in enumerate(urls, 1):
        #we check if we need to resume a url if the script was restarted.
        if url_counter_resume_value is not None:
            #we find the url from where we need to continue from
            if url_counter == url_counter_resume_value:
                #we turn this value to none so we don't do it again when the loop goes to next iteration.
                url_counter_resume_value = None
            else:
                continue

        #make sure that it indeed amazon url
        if "https:" not in url or "amazon.com" not in url:
            continue
        
        #make sure that this url was not used before.
        if os.path.exists("done.csv"):
            dones = pd.read_csv('done.csv').url.unique()
            if url in dones:
                continue 
        
        #shuffle the profiles so we get random profile each time.
        profile_names_list = profiles_input[::-1]
        random.shuffle(profile_names_list)

        #we start looping through the available profile.
        for profile_name in profile_names_list:
            #we check if we need to resume from a specific profile.
            if profile_name_resume_value is not None:
                #we find the profile that needs to be resumed from.
                if profile_name == profile_name_resume_value:
                    #we turn this value to none so we don't do it again when the loop goes to next iteration.
                    profile_name_resume_value = None
                else:
                    continue

            signed_out = []
            if os.path.exists(signout_file):
                signed_out = list(pd.read_csv(signout_file)['profile'].unique())
            #we check if the number of used profile is equal to the total profiles we
            #have in the input file.
            if (len(done_profile) + len(signed_out)) >= len(profile_names_list):
                done_profile = []

            #we check if the current profile selected was not used before
            #to make sure that we don't repeat a file in one go.
            if profile_name in done_profile:
                logger.warning(f"skipped profile [{profile_name}], already in done_profile")
                continue

            if profile_name in signed_out:
                logger.warning(f"skipped profile [{profile_name}], it is signed_out list")
                continue
            
            #gets the id of the profile that we are going to use
            profile_id = profiles.get(profile_name,None)

            #if the id is not found we add it to the done list
            #this basically no such profile exists in the multilogin.
            if not profile_id:
                done_profile.append(profile_name)
                logger.warning(f"skipped profile [{profile_name}], profile_id not found")
                continue
            
            #we spinup the profile here
            browser_connection_url = start_profile(port, profile_id, profile_name)

            #we check if we got the remote url from multilogin or not. if not that will mean the profile was not started.
            if browser_connection_url is None:
                done_profile.append(profile_name)
                continue
            
            #counter for reported number of number of reviews per url
            review_counter = 0

            #we check here if we need to resume from a specific page number in the current selected url
            if read_page_number_and_review_counter_from_file:
                #this value is current flase so we don't perform this in next iteration
                read_page_number_and_review_counter_from_file = False
                _, _, _, page_number_resume_value, review_counter_resume_value = read_from_output_file(output_file_path)

                #if the page number is given we replace the current page number
                #in the url with the reume value
                if page_number_resume_value is not None:
                    page_number = get_page_number_from_url(url)

                    url = url.replace(f"pageNumber={page_number}", f"pageNumber={page_number_resume_value}")

                #we update the number of reviews reported here as well
                if review_counter_resume_value is not None:
                    review_counter = review_counter_resume_value

            #initate the driver instance with the remote url
            driver = webdriver.Remote(command_executor = browser_connection_url)
            logger.info("browser created")
            start_session_time = time.perf_counter()
            try:    
                #begins the reporting procedure for the current url and profile.    
                if start_reporting(driver, profile_name, url, output_file_path, unique_identifier_set, total_urls, url_counter, top_level_domains, review_counter,all_reviews, start_session_time) == False:
                    #here it means that the report process was not a success due to and error
                    #we consider this profile as done and continue to use the same url with new profile.
                    done_profile.append(profile_name)
                    read_page_number_and_review_counter_from_file = True
                    #we close the profile.
                    # close_proifle_by_click()
                    stop_profile(port, profile_id)
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(30)
                    continue
            except:
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(30)
                raise Exception
            #at this stage it mean that the reporting process for current url and profile was
            #a success and close the profile mark the url and profile as done 
            done_profile.append(profile_name)
            
            if os.path.exists("done.csv"):
                pd.DataFrame([{"url":url}]).to_csv("done.csv",mode='a',header=False)
            else:
                pd.DataFrame([{"url":url}]).to_csv("done.csv")
            
            # close_proifle_by_click()
            stop_profile(port, profile_id)

            try:
                driver.quit()
            except:
                pass
            time.sleep(30)
            break
            

def read_from_result_file(output_file_path:str)->list:
    """
    Reads data from the output file\n
    params:\n
    output_file_path: path to the output file\n
    """
    all_data = []
    if os.path.exists(output_file_path):
        with open(output_file_path) as input_file:
            reader = csv.DictReader(input_file)
            for row in reader:
                output_data = {}
                output_data["Total_URLs"] =row["Total_URLs"]
                output_data["URL_Counter"] = row["URL_Counter"]
                output_data["Profile_Name"] = row["Profile_Name"]
                output_data["Product_ID"] = row["Product_ID"]
                output_data["Page_Number"] = row["Page_Number"]
                output_data["Total_Reviews"] = row["Total_Reviews"]
                output_data["Review_Counter"] = row["Review_Counter"]
                output_data["Review_ID"] = row["Review_ID"]
                output_data["Review_Country"] = row["Review_Country"]
                output_data["Review_URL"] = row["Review_URL"]
                output_data["Unique_Identifier"] = row["Unique_Identifier"]
                output_data["Report_Button_Clicked"] = row["Report_Button_Clicked"]
                output_data["Captcha Appeared"] = row["Captcha Appeared"]
                output_data["Captcha Resolved"] = row["Captcha Resolved"]
                output_data["Submit_Button_Clicked"] = row["Submit_Button_Clicked"]
                output_data["TimeStamp_UTC"] = row["TimeStamp_UTC"]
                all_data.append(output_data)

    return all_data


def upload_logs(folder):
    files = glob.glob('logs/*.*')
    for filename in files:

        logger.info(f"uploading file {filename}")
        try:
            upload_file(filename, folder)
        except Exception as e:
            logger.error(f"problem with uploading file {filename}")
            logger.exception(e)

    logger.remove()
    if os.path.exists('logs'):
        for f in glob.glob('logs/*.*'):
            try:
                print('removing file')
                os.remove(f)
            except Exception as e:
                print(e)


#scripts starts from here
if __name__ == '__main__':
    #gets the time when the script was started
    start_time = datetime.now()

    #id of the google sheet
    g_id = None

    #to prevent unwanted errors from the package
    pyautogui.FAILSAFE = False

    #stores the name of the profiles that were used in one iteration
    #so we don't use one profile again and again.
    done_profile = []

    output_file_path = "final_report.csv"

    #checks if we have files that indicates the script was ran before
    #and if we want to resume.
    if os.path.exists(output_file_path) or os.path.exists("progress.json") or os.path.exists("input_f.csv"):
        input_value = input(f"{output_file_path} Exists. Do you want to start from beginning. Press y/n\n")

        if input_value in ["y", "yes", "Y", "YES"]:
            if os.path.exists(output_file_path):
                os.remove(output_file_path)
            if os.path.exists("new_reviews.csv"):
                os.remove("new_reviews.csv")
            if os.path.exists("done.csv"):
                os.remove("done.csv")
            if os.path.exists("input_f.csv"):
                os.remove("input_f.csv")
            if os.path.exists("progress.json"):
                os.remove("progress.json")
            if os.path.exists("Profile_not_signed_in.csv"):
                os.remove("Profile_not_signed_in.csv")
            i_file = pd.read_csv("input.csv")
            i_file = i_file.sample(frac = 1)
            i_file.to_csv('input.csv')

    #it keep the track of the google sheet id and if we want to add heads to gsheet
    if not os.path.exists("progress.json"):
        folder = search_folders("1tz84NM633GbIZof0PMsyV_3O9BBKYLGg",
                                        MACHINE)
        g_id = create_google_spreadsheet(
                    f"{start_time.strftime('%Y-%m-%d %H:%M:%S')} Report Abuse Report {MACHINE}",
                    parent_folder_ids=folder)
        
        progress = {'gid':g_id,"header":True}
        file = open("progress.json","w")
        file.write(json.dumps(progress))
        file.close()
    else:
        file = open("progress.json","r")
        content = json.loads(file.read())
        g_id = content['gid']
        file.close()

    #gets all reviews ids from the database that we have
    all_reviews = add_reviews()

    #this while true here is if an error appears in the script
    #that is solvable by restarting the script this will handle it.
    while True:
        try:
            

            if main(done_profile,all_reviews) == False:
                #this will mean the starting of report process was failed and we stop the script
                pass
            else:
                #this will mean the process was a success and upload the report to gdrive and update the dashbaord.
                tracker = pd.DataFrame(read_from_result_file("final_report.csv"))
                tracker['machine'] = MACHINE
                update_sheet(tracker, g_id)
                update_dashboard(DAS_ID,"Done",len(tracker),len(pd.read_csv("input.csv")),len(pd.read_csv("input.csv")),MACHINE)
                try:
                    #upload all the new reviews collected to the sheet selected for it.
                    data = pd.read_csv("new_reviews.csv")
                    add_new_reviews(MACHINE,data)
                except Exception as e:
                    logger.exception(e)
                    print(e)
                    pass
                upload_report_to_database()

                #upload logs to the drive Roman will handle the case
                folder = search_folders("1tz84NM633GbIZof0PMsyV_3O9BBKYLGg",
                                        f"{MACHINE}_logs")

                # upload file with list of not signed in profiles into drive
                if os.path.exists('Profile_not_signed_in.csv'):
                    upload_file('Profile_not_signed_in.csv', folder)

                upload_logs(folder)
            break

        except Exception as e:
            print(traceback.format_exc())
            logger.exception(e)
            logger.info("Restarting Script...")
            logger.info("#" * 100)
