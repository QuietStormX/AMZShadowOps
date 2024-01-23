import os
import time
from datetime import datetime

import pandas as pd
import requests
from amazoncaptcha import AmazonCaptcha
from loguru import logger
from selenium import webdriver
from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.common.by import By

logger.add(
    f"logs/status_check_{datetime.now().strftime('%d_%m_%Y')}.log",
)


def start_profile(port: int, profile_id: str, profile_name: str, max_retries: int = 5) -> str:
    """
    starts a multlogin profile\n
    params:\n
    port: multilogin API port \n
    profile_id: uuid of the profile \n
    profile_name: name of the profile \n
    max_retrires: number of retries to do if the request fails \n
    """
    mla_url = f"http://127.0.0.1:{port}/api/v1/profile/start?automation=true&profileId=" + profile_id  # multilogin API endpoint to spin up a profile

    for retry_counter in range(max_retries):  # retires loop if the request fails
        try:
            response = requests.get(mla_url)  # makes request to the API

            response_json = response.json()  # converts the response to the json

            if response.status_code != 500:  # if the request is not 500 we accept the response
                return response_json["value"]  # the remote url for the browser is returned

        except requests.exceptions.Timeout:
            logger.warning(f"Profile Name = {profile_name}. Request Timeout.")

        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Profile Name = {profile_name}. Please Make Sure MultiLogin API Is Running. Failed To Make Request To The API.")

        except requests.exceptions:
            logger.error(f"Profile Name = {profile_name}. Request Failed Due To.")

        except Exception as e:
            logger.error(f"Profile Name = {profile_name}. Generic Exception Raised.")
            logger.exception(e)

        if retry_counter >= max_retries - 1:
            logger.info(f"Profile Name = {profile_name}. Profile Not Opened.")
            return

        logger.warning(f"Profile Name = {profile_name}. Unable To Connect. Retrying...")

        time.sleep(10)  # if the requests fail we wait for 10 seconds and try again.


def stop_profile(port: int, profile_id: str) -> None:
    """
    Stops a multilogin profile\n
    params:\n
    port: port the multilogin api\n
    profiles_id:uuid of the multilogin profile\n

    """
    mla_url = f"http://127.0.0.1:{port}/api/v1/profile/stop?profileId={profile_id}"  # multilogin API endpoint that stops a profile

    try:
        requests.get(mla_url)  # makes request to the url mentioned above
    except Exception:
        pass


def get_profiles(port: int) -> dict:
    """
    Gets all profiles from multilogin6\n
    params:
    port: multilogin api port
    """
    url = f"http://127.0.0.1:{port}/api/v2/profile"  # multililogin API endpoint to retreieve all the profiles

    try:
        for i in range(3):
            # makes request using the python request library. to the url mentioned above
            response = requests.get(url)

            if response.status_code != 200:  # if the request was not successful
                if response.status_code == 504:  # it took more than 120 seconds to complete the request
                    time.sleep(10)  # sleeps for 10 seconds.
                    continue
                logger.info(f"Response Status Code = {response.status_code}")  # print the status code form the API
                logger.warning(
                    "MultiLogin Not Logged In.")  # most probably multilogin is logged out or the port number is wrong
                return

            break  # we stop the script at the point because there is no point in continuing if multilogin is not working

        profiles_list = response.json()  # convert response from multilogin to json

        profiles_dict = {}  # initalizing the a dictionary to store the {"profile_name":"uuid"}

        for profile in profiles_list:  # goes through each profile in the list of profiles
            profiles_dict[profile['name'].strip()] = profile['uuid']  # stores relavent information in the dictionary

        return profiles_dict  # returns the dictionary

    except requests.exceptions.Timeout:
        logger.error("Request To Get Profiles Timeout.")

    except requests.exceptions.ConnectionError:
        logger.error("Please Make Sure MultiLogin API Is Running. Failed To Make Request To The API.")  #

    except requests.exceptions as re:
        logger.error("Request Failed Due To.")
        logger.error(re)

    except Exception as e:
        logger.error("Generic Exception Raised.")
        logger.exception(e)


def solve_captcha(driver, max_retries=5) -> bool:
    """
    tries to solve captcha\n
    pramas:\n
    driver: selenium driver object \n
    max_retries: number of retries we need to do \n
    """

    for retry_counter in range(max_retries):  # loop to manage the retries
        logger.info(f"Trying to Solve Captcha. Retry Counter {retry_counter + 1}")

        try:
            href = driver.find_element(By.XPATH, ".//img[contains(@src, 'captcha')]").get_attribute(
                'src')  # gets the captcha image source from the page

            captcha = AmazonCaptcha.fromlink(href)  # provides the image url to the amazonCaptcha library

            solution = captcha.solve()  # uses the amazonCaptcha library to extract text from the image

            logger.info(f"Captcha Solution - {solution}")

            driver.find_element(By.CSS_SELECTOR, 'input#captchacharacters').send_keys(
                solution)  # find the text box to enter the captcha text

            time.sleep(1)  # sleep for 1 seconds

            element = driver.find_element(By.CSS_SELECTOR,
                                          'button.a-button-text')  # find the submit button to submit the captcha form

            webdriver.ActionChains(driver).move_to_element(element).click(element).perform()

            time.sleep(1)  # sleep for 1 seconds

            if "Try different image" in driver.page_source:  # confirm if the captcha was indeed solved
                time.sleep(5)  # sleep for 5 seconds and the loop will continue
            else:
                logger.info("Captcha Solved")
                return True  # captcha was solved so we return ture

        except Exception as e:  # in case any error happends
            logger.exception(e)  # we print the traceback of the error

    logger.warning("Captcha Not Solved")  # if we reach to this point that will mean captcha was not solved

    return False  # return false as captcha was not solved


def check_status(profile_names):
    if os.path.exists('status_result.csv'):
        os.remove('status_result.csv')

    port = 35111
    profiles = get_profiles(port)
    for profile_name in profile_names:
        profile_id = profiles.get(profile_name, None)

        if not profile_id:
            logger.warning(f'profile id not found for {profile_name}')
            if os.path.exists("status_result.csv"):
                pd.DataFrame([{
                    'profile': profile_name,
                    'is_logged_in': None,
                    'Note': 'profile_id not found',
                }]
                ).to_csv("status_result.csv", mode='a', header=False, index=False)
            else:
                pd.DataFrame([{
                    'profile': profile_name,
                    'is_logged_in': None,
                    'Note': 'profile_id not found',
                }]).to_csv("status_result.csv", index=False)

            continue

        try:
            profile_url = start_profile(port, profile_id, profile_name)

            driver = webdriver.Remote(command_executor=profile_url, options=ChromiumOptions())

            driver.get("https://www.amazon.com/gp/css/order-history?ref_=nav_orders_first")
            time.sleep(2)
            solved = "Try different image" not in driver.page_source
            for a in range(3):
                if "Try different image" in driver.page_source:
                    logger.info(f"Captcha Appeared. Profile Name: {profile_name}")

                    if solve_captcha(driver):
                        logger.info(f"Captcha Solved. Profile Name: {profile_name}")

                        driver.get("https://www.amazon.com/gp/css/order-history?ref_=nav_orders_first")
                        time.sleep(2)
                        solved = True
                        break
                    else:
                        logger.warning(f"Captcha Not Solved. Profile Name: {profile_name}")
                else:
                    break

            if not solved:
                if os.path.exists("status_result.csv"):
                    pd.DataFrame([{
                        'profile': profile_name,
                        'is_logged_in': False,
                        'Note': 'Captcha not solved',
                    }]
                    ).to_csv("status_result.csv", mode='a', header=False, index=False)
                else:
                    pd.DataFrame([{
                        'profile': profile_name,
                        'is_logged_in': False,
                        'Note': 'Captcha not solved',
                    }]).to_csv("status_result.csv", index=False)

                continue

            if driver.title == "Your Orders":
                logger.info(f"profile {profile_name} is logged in")
                if os.path.exists("status_result.csv"):
                    pd.DataFrame([{
                        'profile': profile_name,
                        'is_logged_in': True,
                        'Note': None,
                    }]
                    ).to_csv("status_result.csv", mode='a', header=False, index=False)
                else:
                    pd.DataFrame([{
                        'profile': profile_name,
                        'is_logged_in': True,
                        'Note': None,
                    }]).to_csv("status_result.csv", index=False)
            else:
                heading = driver.find_element(By.TAG_NAME, "h1").text.strip()
                if driver.title == "Amazon Sign-In" or heading == "Sign in":
                    logger.warning(f"profile {profile_name} is logged out")
                    if os.path.exists("status_result.csv"):
                        pd.DataFrame([{
                            'profile': profile_name,
                            'is_logged_in': False,
                            'Note': None,
                        }]
                        ).to_csv("status_result.csv", mode='a', header=False, index=False)
                    else:
                        pd.DataFrame([{
                            'profile': profile_name,
                            'is_logged_in': False,
                            'Note': None,
                        }]).to_csv("status_result.csv", index=False)

            logger.info(f"stopping profile {profile_name}")
            stop_profile(port, profile_id)
        except Exception as e:
            logger.warning(f"error for profile {profile_name}")
            if os.path.exists("status_result.csv"):
                pd.DataFrame([{
                    'profile': profile_name,
                    'is_logged_in': None,
                    'Note': f'error occur - {repr(e)}',
                }]
                ).to_csv("status_result.csv", mode='a', header=False, index=False)
            else:
                pd.DataFrame([{
                    'profile': profile_name,
                    'is_logged_in': None,
                     'Note': f'error occur - {repr(e)}',
                }]).to_csv("status_result.csv", index=False)

            continue

        try:
            driver.quit()
        except Exception as e:
            try:
                driver.quit()
            except Exception as e:
                pass


if __name__ == '__main__':
    df = pd.read_csv('status_check_input.csv')
    profile_names = df['Profile'].unique()
    check_status(profile_names)
