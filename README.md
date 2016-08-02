# ScrapeCheckiO
A script to download your CheckiO solutions.

[CheckiO](https://checkio.org) is a website where Python coders can solve a wide range of programming challenges, and this script allows a user to backup their solutions to a local folder. Once the user is logged in, the script parses the list of mission sections and submitted solutions, and downloads each solution into a folder named after its section. Because of the way CheckiO presents the solution code, a Javascript-enabled browser needs to prepare the page before it can be parsed. This script relies on [Firefox](https://mozilla.com/firefox) and [Selenium](https://pypi.python.org/pypi/selenium) to handle this.

Basic usage
-----------
The browser needs to be logged into CheckiO to access the user's missions, and there are a few options for this. The simplest is to just run the script - the browser will open the login page, and you can manually enter your details before continuing. You can also provide your username and password with the `--login` option to automate the process, but this will only handle CheckiO site credentials - Single Sign-On is not currently supported. An alternative is to use the `--sessionid` option and provide the contents of the *sessionid* cookie from a logged-in session, which will be used by Selenium's browser.

The script will attempt to scrape each solution page in turn, but will eventually fail if the page fails to load fully within a certain timeframe. Any failed downloads will be reported when the script completes. Existing Python files will be overwritten, unless the contents are identical (to preserve the timestamp).

Run the script with the `--help` flag for the full list of options.
