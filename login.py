##########################################
# This file logs a multilogin profile    #
# into amazon                            #
##########################################


import csv
import time
import traceback
import pyautogui
from selenium import webdriver
from amazoncaptcha import AmazonCaptcha
from selenium.webdriver.common.by import By
from selenium.common import WebDriverException, NoSuchWindowException, NoSuchElementException
import pandas as pd
from typing import Union,List,Tuple
import os
from googlesheet.core import get_credentials_of_profiles

get_credentials_of_profiles()

def goto_page(driver, url:str, perform_ready_state_check:bool = True):
    """
    loads a url\n
    pramas:\n
    driver: selenium driver object\n 
    url: url that needs to be loaded \n 
    perfomr_ready_state_check: check the ready state of the page through JS\n 
    """
    while True:
        try:
            driver.get(url)
            break
        
        except WebDriverException:
            if "This site can’t be reached" in driver.page_source:
                raise Exception
            time.sleep(5)

    while perform_ready_state_check:
        page_state = driver.execute_script("return document.readyState;")

        if page_state == "complete":
            if "This site can’t be reached" in driver.page_source:
                raise Exception
            break

        time.sleep(0.1)


def check_if_page_is_a_sign_in_page(driver)->bool:
    """
    check if the current page is amazon signin page or not\n
    pramas:\n
    driver: selenium driver object\n 
    """
    heading = driver.find_element(By.TAG_NAME, "h1").text.strip()

    return driver.title == "Amazon Sign-In" or heading == "Sign in"


def read_credentials_file()->dict:
    """
    collects all the credentials of the profiles from the credentials.csv
    """
    input_file_path = "Credentials.csv"
    df = pd.read_csv(input_file_path).drop_duplicates(subset=['ML Profile','Email'],keep='last')
    df.to_csv("f_Credentials.csv",index=False)
    input_file_path = "f_Credentials.csv"
    credentials = {}

    with open(input_file_path) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            multilogin_profile_name = row["ML Profile"]
            email = row["Email"]
            password = row["Password"]

            if (not multilogin_profile_name) or (not email) or (not password):
                continue

            credentials[multilogin_profile_name] = {"email": email, "password": password}

    return credentials

#
def focused_click(driver, element):
    """
    clicks on a element. if the browser is hidden it will first bring it forth and then click on the element \n
    pramas:\n
    driver:selenium driver object \n
    element:element that needs to be clicked on \n
    """
    try:
        if driver.title in pyautogui.getActiveWindowTitle(): #if the active window title is not same as the driver window title
            pyautogui.getWindowsWithTitle(driver.title)[0].activate() # we find the window and bring it forth
    except Exception:
        pass

    element.click()


def ensure_new_tab_gets_opened(driver, main_window_handle):
    """
    make sure that the new tab is opened\n
    pramas:\n
    driver:selenium driver object \n
    main_window_handle: main handle of the browser where amazon page is open \n
    """
    while driver.current_window_handle == main_window_handle:
        driver.switch_to.new_window('tab')
        time.sleep(2)


def ensure_new_tab_gets_closed(driver, main_window_handle):
    """
    make sure that the new tab is closed\n
    pramas:\n
    driver:selenium driver object \n
    main_window_handle: main handle of the browser where amazon page is open \n
    """
    try:
        while True:
            driver.close()

    except NoSuchWindowException:
        pass

    driver.switch_to.window(main_window_handle)

    while driver.current_window_handle != main_window_handle:
        driver.switch_to.window(main_window_handle)


def get_otp_from_gmail(driver)->Union[str,None]:
    """
    goes to gmail url and collects the amazon otp form the mail box\n
    pramas:\n
    driver:selenium driver object \n
    """
    gmail_inbox_page_url = "https://mail.google.com/mail/u/0/#inbox"

    main_window_handle = driver.current_window_handle

    ensure_new_tab_gets_opened(driver, main_window_handle)

    goto_page(driver, gmail_inbox_page_url)

    time.sleep(2)

    #finds the email from the list of emails that matches the otp title pattern and selects the second item
    email_tag = driver.find_elements(By.XPATH, './/td//span[contains(text(), "amazon.com: Sign-in attempt")]')[1]

    focused_click(driver, email_tag)

    time.sleep(2)

    #finds all the paragraphs
    paragraph_tags = driver.find_elements(By.TAG_NAME, "p")

    otp = None
    #goes through all the paragrahs and find the ones that have only 6 characters which means that it is the otp
    for paragraph_tag in paragraph_tags:
        paragraph_text = paragraph_tag.text.strip()

        if len(paragraph_text) == 6:
            otp = paragraph_text

    #close the tab
    ensure_new_tab_gets_closed(driver, main_window_handle)

    return otp


def skip_email_input(driver) -> bool:
    """
    this function check if we need to enter email for the signin page of amazon.\n
    params:\n
    driver:selenium driver object \n
    """
    return "Hello," in driver.page_source or "Please enter your password to continue" in driver.page_source


def handle_email_situation(driver, email):
    """
    This function enters the amazon email in the amazon sign page.\n
    params:\n
    driver:selenium driver object \n
    email:email of the profile that needs to be logged in.\n
    """

    if skip_email_input(driver):
        return

    email_input = driver.find_element(By.ID, "ap_email")

    focused_click(driver, email_input)

    time.sleep(1)

    email_input.clear()

    time.sleep(1)

    email_input.send_keys(email)

    time.sleep(1)

    continue_button = driver.find_element(By.ID, "continue")

    focused_click(driver, continue_button)

    time.sleep(1)


def handle_password_situation(driver, password):
    """
    This function enters the amazon email in the amazon sign page.\n
    params:\n
    driver: selenium driver object \n
    password: password of the profile that needs to be logged in.\n
    """
    password_input = driver.find_element(By.ID, "ap_password")

    focused_click(driver, password_input)

    time.sleep(1)

    password_input.clear()

    time.sleep(1)

    password_input.send_keys(password)

    time.sleep(1)

    #if the email input was present it means we can also check the remember me box
    if not skip_email_input(driver):
        remember_me_check_box = driver.find_element(By.XPATH, './/input[@name="rememberMe"]')

        if not remember_me_check_box.is_selected():
            focused_click(driver, remember_me_check_box)
            time.sleep(1)

    sign_in_button = driver.find_element(By.ID, "signInSubmit")

    focused_click(driver, sign_in_button)

    time.sleep(1)


def handle_keep_hackers_out_situation(driver):
    """
    click on "not now" button when asked for phone number to keep the hacker out.
    params:\n
    driver: selenium driver object \n                          
    """
    if "Keep hackers out" in driver.page_source:
        not_now_button = driver.find_element(By.ID, "ap-account-fixup-phone-skip-link")
        focused_click(driver, not_now_button)
        time.sleep(1)



def solve_captcha(driver, max_retries = 5):
    """
    tries to solve captcha\n
    pramas:\n
    driver: selenium driver object \n
    max_retries: number of retries we need to do \n
    """

    for retry_counter in range(max_retries):
        print(f"Trying to Solve Captcha. Retry Counter {retry_counter + 1}")

        try:
            href = driver.find_element(By.XPATH, ".//img[contains(@src, 'captcha')]").get_attribute('src') #gets the captcha image source from the page

            captcha = AmazonCaptcha.fromlink(href) # provides the image url to the amazonCaptcha library

            solution = captcha.solve() #uses the amazonCaptcha library to extract text from the image

            print(f"Captcha Solution - {solution}")

            driver.find_element(By.CSS_SELECTOR, 'input#captchacharacters').send_keys(solution) #find the text box to enter the captcha text

            time.sleep(1) #sleep for 1 seconds

            element = driver.find_element(By.CSS_SELECTOR, 'button.a-button-text') #find the submit button to submit the captcha form
 
            focused_click(driver, element) #click on the submit button

            time.sleep(1) #sleep for 1 seconds

            if check_if_page_contains_captcha(driver): #confirm if the captcha was indeed solved
                time.sleep(5)  #sleep for 5 seconds and the loop will continue

            else:
                print("Captcha Solved") 
                return True #captcha was solved so we return ture

        except Exception: #in case any error happends
            print(traceback.format_exc()) #we print the traceback of the error


    print("Captcha Not Solved") #if we reach to this point that will mean captcha was not solved

    return False #return false as captcha was not solved



def check_if_page_contains_captcha(driver):
    """
    checks if the page has captcha or not\n
    pramas:\n
    driver:selenium driver object \n
    """
    return "Try different image" in driver.page_source # if the text exist it will mean there is captcha and return true else false


def handle_captcha_situation(driver, profile_name:str):
    """
    checks if the page has captcha or not.if does try to solve it\n
    pramas:\n
    driver:selenium driver object \n
    profile_name:name of the profile \n
    """
    while check_if_page_contains_captcha(driver):
        print(f"Captcha Appeared. Profile Name: {profile_name}")

        if solve_captcha(driver):
            print(f"Captcha Solved. Profile Name: {profile_name}")

        else:
            print(f"Captcha Not Solved. Profile Name: {profile_name}")

def handle_http_error_407_on_main_window(driver):
    """
    checks if  the page has 407 error if does then loads google.com and reloads the
    original url.
    pramas:\n
    driver:selenium driver object \n
    """
    if "HTTP ERROR 407" in driver.page_source:
        current_url = driver.current_url
        goto_page(driver, "https://www.google.com/")
        time.sleep(2)
        goto_page(driver, current_url)
        time.sleep(2)

        #it will mean that 407 error was not solved
        if "HTTP ERROR 407" in driver.page_source:
            return 1
    #it will mean that 407 error was solved
    return 0


def handle_otp_situation(driver):
    """
    checks if amazon is requesting otp after trying to signin.
    if does then will goto gmail and try to get the otp from there.
    and submmit the amazon otp form.
    pramas:\n
    driver:selenium driver object \n
    """
    page_source = driver.page_source

    if "Enter verification code" in page_source or "Resend code" in page_source or "Submit code" in page_source:
        otp = get_otp_from_gmail(driver)
        print(otp)
        input_tags = driver.find_elements(By.ID, 'input-box-otp')

        input_tags[0].send_keys(otp)

        submit_code_button = driver.find_element(By.ID, 'cvf-submit-otp-button')

        focused_click(driver, submit_code_button)





def handle_switch_accounts_situation(driver):
    """
    checks if there are multiple accounts on same profile. will slect the first one
    pramas:\n
    driver:selenium driver object \n
    """
    if "Switch accounts" in driver.page_source:
        name_tag = driver.find_element(By.XPATH, './/div[@class="a-row a-size-base-plus cvf-text-truncate"]')
        focused_click(driver, name_tag)
        time.sleep(1)


def main(driver,profile_name)->bool:
    """
    main function that executes functions in order to log a profile's amazon account in.
    if the amazon profiles gets logged in will return True else False
    pramas:\n
    driver:selenium driver object \n
    profile_name:name of the profile \n
    """
    output_file = "Profile_not_signed_in.csv"
    pyautogui.FAILSAFE = False

    order_history_page_url = "https://www.amazon.com/gp/css/order-history?ref_=nav_orders_first"


    credentials = read_credentials_file()
    creds = credentials.get('profile_name', None)

    if creds is None:
        if os.path.exists(output_file):
            pd.DataFrame([{"profile": profile_name}]).to_csv(output_file, mode='a', index=False, header=False)
        else:
            pd.DataFrame([{"profile": profile_name}]).to_csv(output_file, index=False)
        return False

    email = creds['email']
    password = creds['password']
    try:

        goto_page(driver, order_history_page_url)

        # http_error_407_status = handle_http_error_407_on_main_window(driver)
        #
        # if http_error_407_status == 1:
        #     return False

        handle_captcha_situation(driver, profile_name)

        if not check_if_page_is_a_sign_in_page(driver):
            return True

        handle_captcha_situation(driver, profile_name)

        handle_switch_accounts_situation(driver)

        handle_email_situation(driver, email)

        handle_captcha_situation(driver, profile_name)

        handle_keep_hackers_out_situation(driver)

        handle_captcha_situation(driver, profile_name)

        handle_password_situation(driver, password)

        handle_captcha_situation(driver, profile_name)

        handle_keep_hackers_out_situation(driver)

        handle_captcha_situation(driver, profile_name)

        # TODO skipping OTP check and google login for now
        page_source = driver.page_source
        if "Enter verification code" in page_source or "Resend code" in page_source or "Submit code" in page_source:
            if os.path.exists(output_file):
                pd.DataFrame([{"profile": profile_name}]).to_csv(output_file, mode='a', index=False, header=False)
            else:
                pd.DataFrame([{"profile": profile_name}]).to_csv(output_file, index=False)
            return False

        # handle_otp_situation(driver)

        if driver.title == "Your Orders":
            return True
        else:
            if os.path.exists(output_file):
                pd.DataFrame([{"profile":profile_name}]).to_csv(output_file,mode='a',index=False,header=False)
            else:
                pd.DataFrame([{"profile":profile_name}]).to_csv(output_file,index=False)
            return False

    except Exception as e:
        print(e)
        print("Profile Did Not Get Signed In.")

        if os.path.exists(output_file):
            pd.DataFrame([{"profile":profile_name}]).to_csv(output_file,mode='a',index=False,header=False)
        else:
            pd.DataFrame([{"profile":profile_name}]).to_csv(output_file,index=False)

        return False