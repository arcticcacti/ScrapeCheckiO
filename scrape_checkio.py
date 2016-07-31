import requests
import re
import time
import os
import sys
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException

USERNAME_PATTERN = r'https://checkio.org/user/(?P<username>.*?)/'
MISSION_NAME_PATTERN = r'https://checkio.org/mission/(?P<mission_name>.*?)/'

USER_PAGE = 'https://checkio.org/user/'
LOGIN_PAGE = 'https://checkio.org/profile/login/'
MISSIONS_PAGE = 'https://checkio.org/user/{name}/list/'
SOLUTION_PAGE = 'https://checkio.org/mission/{name}/solve/'

PAGE_RETRIES = 3
RETRY_DELAY_SECS = 5
VERBOSE = False


def get_browser(sessionid=None, user=None, password=None):
    """ Get a webdriver and log in to the CheckiO site.
    This will automatically use the sessionid cookie if provided, otherwise
    it will use the user/pass details to log in. If these are not provided,
    it will wait for the user to confirm they have logged into their account.

    Args:
    sessionid -- Optional contents of the logged-in user's sessionid cookie.
    user      -- Optional CheckiO username for the login page.
    password  -- Optional CheckiO password.

    Returns:
    The open webdriver instance.
    """
    browser = webdriver.Firefox()
    browser.get(USER_PAGE)
    # just use the login cookie if possible
    if sessionid:
        browser.add_cookie({'name':'sessionid', 'value':sessionid});
        return browser

    # need to log in somehow, try to use supplied credentials
    if user and password:
        try:
            browser.find_element_by_id("id_username").send_keys(user)
            browser.find_element_by_id("id_password").send_keys(password)
            browser.find_element_by_class_name("abuth__btn").click()
            return browser
        except NoSuchElementException:
            print("ERROR: couldn't find expected elements on the login page, you need to log in manually")
        
    # default to asking the user to log in manually
    input("\nPlease log in to the CheckiO site, then hit Enter to continue.")        
    return browser


def get_username(browser):
    """ Get the username of the currently logged-in user.

    Args:
    browser -- A webdriver browser, which should be logged in.

    Returns:
    The user's username, or None if it can't be parsed (probably not logged in).
    """
    # load the user profile page, and parse the username from its URL
    browser.get(USER_PAGE)
    try:
        return re.match(USERNAME_PATTERN, browser.current_url).group('username')
    except AttributeError:
        if browser.current_url.startswith(LOGIN_PAGE):
            print("ERROR: It looks like you're not logged in.")
        return None


def get_missions(browser, username):
    """ Get a dict of mission categories, and the list of missions in each.

    Args:
    browser -- A webdriver browser, which should be logged in.

    Returns:
    A dict of mission category names, mapping to lists of missions.
    The missions are dicts containing a 'title' field (the title in the missions listing),
    and a 'url_name' field for the mission name section of the URL's path.
    """
    # jump straight to the completed missions listing, instead of navigating slowly
    url = MISSIONS_PAGE.format(name=username)
    browser.get(url)

    # get all the mission sections
    regex = re.compile(MISSION_NAME_PATTERN)
    section_list = {}
    try:
        for section in browser.find_elements_by_class_name('section'):
            title = section.find_element_by_class_name('section-header').text
        
            # get all the missions in this section
            task_list = []
            for task in section.find_elements_by_class_name('block_progress_main'):
                task_title = task.find_element_by_tag_name('img').get_attribute('title')
                
                # get the mission URL, but extract the code so we can jump straight to the solution page
                href = task.find_element_by_tag_name('a').get_attribute('href')
                task_code = regex.match(href).group('mission_name')
            
                mission = {'title':task_title, 'url_name':task_code}
                task_list.append(mission)            
            section_list[title] = task_list
        return section_list
    except NoSuchElementException:
        print("ERROR: unable to parse mission list, unexpected page structure")
        return {}
            

def get_solution(browser, mission):
    """ Get the user's code currently saved in a mission's solution.

    Args:
    browser -- A webdriver browser, which should be logged-in.
    mission -- A mission dict, containing its title and URL path name.

    Returns:
    The currently saved code, as a list of lines.
    """
    # this lets us jump straight to the solution, instead of slowly navigating via the mission page
    mission_url = SOLUTION_PAGE.format(name=mission)
    if VERBOSE:
        print("Downloading: {}".format(mission_url))
    browser.get(mission_url)
    
    # the site does a bunch of JS after it has loaded, so elements can go missing halfway through
    # if we run into an error, give up and delay before retrying - either return all lines, or nothing
    attempts = 0
    while attempts <= PAGE_RETRIES:
        try:
            attempts += 1
            lines = browser.find_elements_by_class_name('ace_line')
            return [line.text for line in lines]
        except StaleElementReferenceException:
            if VERBOSE:
                print('Attempt {} failed, page not ready'.format(attempts))
            time.sleep(RETRY_DELAY_SECS)
    if VERBOSE:
        print('Failed after {} attempts'.format(attempts))
    return None


def create_and_switch_to_dir(dir_path):
    """ Create a directory in the current directory, and set that as the current dir.

    Args:
    dir_path -- The path to the directory that will be created.

    Raises:
    IOError  -- If the directory doesn't exist and couldn't be created.
    """
    try:
        os.makedirs(dir_path, exist_ok=True)
        os.chdir(dir_path)
    except (NotADirectoryError, FileNotFoundError):
        raise IOError()


def write_solution_to_file(browser, mission):
    """ Get the user's solution code for a mission, and write it to a file.
    This will use the mission's URL path name as the filename,
    and adds an initial comment line with the mission's title.

    Args:
    browser -- A webdriver browser, which should be logged-in.
    mission -- A mission dict, containing its title and URL path name.
    """
    # Get the code listing as a list of lines, adding the mission title at the top    
    downloaded = get_solution(browser, mission['url_name'])
    if not downloaded:
        raise IOError()
    download_time = datetime.now().strftime('%c')
    code = ['# "{}" downloaded: {}'.format(mission['title'], download_time)]
    code.extend(downloaded);
    filename = mission['url_name'] + '.py'

    # if the file exists and is identical, don't touch it
    try:
        with open(filename, mode='r') as f:
            if f.read().splitlines() == code:
                return
    except OSError:
        pass
                
    # overwrite the file with the scraped code
    try: 
        with open(filename, mode='w') as f:
            for line in code:
                print(line, file=f)
    except IOError:
        # couldn't save the file - clean up and let the caller know
        os.remove(filename)
        raise


def download_section(section_name, missions):
    """ Download a section's missions, creating a new folder in the current directory.

    Args:
    section_name -- used to generate a name for the folder
    missions     -- the list of missions in this section

    Returns:
    a list of errors, which may be empty
    """
    print("Getting section ({}) with {} missions".format(section_name, len(mission_list)))
    # create the section's folder, fail if unable
    original_dir = os.getcwd()
    dir_name = "".join(char for char in section_name if char.isalnum())
    try:
        create_and_switch_to_dir(dir_name)
    except IOError:
        return ["Unable to create folder for section: {}".format(section_name)]
    
    errors = []
    for mission in mission_list:
        try:
            write_solution_to_file(browser, mission)
        except IOError:
            errors.append("{}: {}".format(section_name, mission['title']))
    # move back up to the original folder, so we can create the next subfolder
    os.chdir(original_dir)
    return errors
    


def get_args():
    """ Defines and processes command-line options and arguments """
    parser = argparse.ArgumentParser(
        description="Automatically download a user's CheckiO Python solutions, using Firefox",
        epilog="You can provide either the sessionid cookie data from an already logged-in "
               "browser session, or login details for the CheckiO site. If you would prefer "
               "to log in manually (for example, using 3rd-party authorisation like Facebook), "
               "omit both options and you will be prompted to log in and continue the script."
        )
    parser.add_argument('-d', '--dest_dir', metavar='path',
                        help=("optional folder path to download to. "
                              "Omitting this downloads to the current directory.")
                        )
    parser.add_argument('-v', '--verbose', action="store_true")
    credentials = parser.add_mutually_exclusive_group()
    credentials.add_argument('-s', '--sessionid', metavar='cookie_data', 
                        help=("log in using sessionid cookie value, e.g. if you use 3rd-party auth.")
                        )    
    credentials.add_argument('-l', '--login', nargs=2, metavar=('username', 'password'), default=[], 
                        help=("CheckiO username and password to log in with.")
                        )
    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()
    VERBOSE = args.verbose
    # move to the specified dir, if any
    if args.dest_dir:
        try:
            create_and_switch_to_dir(args.dest_dir)
        except IOError:
            sys.exit("ERROR: Unable to create destination folder")
    
    browser = get_browser(args.sessionid, *args.login)
    username = get_username(browser)
    if not username:
        sys.exit("ERROR: Unable to get username - was login successful?")

    # get the groups of missions, and download each group to its own folder
    missions = get_missions(browser, username)
    errors = []    
    for section_name, mission_list in missions.items():
        if not section_name:
            errors.append("Unknown section containing:")
            for mission in mission_list:
                errors.append("-- {}".format(mission['title']))
        else:
            errors.extend(download_section(section_name, mission_list))

    # TODO: results dict, with added/updated/error

    print("\nDownload complete.")
    if errors:
        print("\nThere was a problem saving the following missions:")
        for error in errors:
            print(error)
