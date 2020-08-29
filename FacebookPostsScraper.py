import requests
from bs4 import BeautifulSoup
import pickle
import os
from urllib.parse import urlparse, unquote
from urllib.parse import parse_qs
import pandas as pd
import json
import datetime

class FacebookPostsScraper:

    # We need the email and password to access Facebook, and optionally the text in the Url that identifies the "view full post".
    def __init__(self, email, password, post_url_text='Full Story'):
        self.email = email
        self.password = password
        self.headers = {  # This is the important part: Nokia C3 User Agent
            'User-Agent': 'NokiaC3-00/5.0 (07.20) Profile/MIDP-2.1 Configuration/CLDC-1.1 Mozilla/5.0 AppleWebKit/420+ (KHTML, like Gecko) Safari/420+'
        }
        self.session = requests.session()  # Create the session for the next requests
        self.cookies_path = 'session_facebook.cki'  # Give a name to store the session in a cookie file.

        # At certain point, we need find the text in the Url to point the url post, in my case, my Facebook is in
        # English, this is why it says 'Full Story', so, you need to change this for your language.
        # Some translations:
        # - English: 'Full Story'
        # - Spanish: 'Historia completa'
        self.post_url_text = post_url_text

        # Evaluate if NOT exists a cookie file, if NOT exists the we make the Login request to Facebook,
        # else we just load the current cookie to maintain the older session.
        if self.new_session():
            self.login()

        self.BigMoneyIndex_posts = {}

    # We need to check if we already have a session saved or need to log to Facebook
    def new_session(self):
        if not os.path.exists(self.cookies_path):
            return True

        f = open(self.cookies_path, 'rb')
        cookies = pickle.load(f)
        self.session.cookies = cookies
        return False

    # Utility function to make the requests and convert to soup object if necessary
    def make_request(self, url, method='GET', data=None, is_soup=True):
        if len(url) == 0:
            raise Exception(f'Empty Url')

        if method == 'GET':
            resp = self.session.get(url, headers=self.headers)
        elif method == 'POST':
            resp = self.session.post(url, headers=self.headers, data=data)
        else:
            raise Exception(f'Method [{method}] Not Supported')

        if resp.status_code != 200:
            raise Exception(f'Error [{resp.status_code}] > {url}')

        if is_soup:
            return BeautifulSoup(resp.text, 'lxml')
        return resp

    # The first time we login
    def login(self):
        # Get the content of HTML of mobile Login Facebook page
        url_home = "https://m.facebook.com/"
        soup = self.make_request(url_home)
        if soup is None:
            raise Exception("Couldn't load the Login Page")

        # Here we need to extract this tokens from the Login Page
        lsd = soup.find("input", {"name": "lsd"}).get("value")
        jazoest = soup.find("input", {"name": "jazoest"}).get("value")
        m_ts = soup.find("input", {"name": "m_ts"}).get("value")
        li = soup.find("input", {"name": "li"}).get("value")
        try_number = soup.find("input", {"name": "try_number"}).get("value")
        unrecognized_tries = soup.find("input", {"name": "unrecognized_tries"}).get("value")

        # This is the url to send the login params to Facebook
        url_login = "https://m.facebook.com/login/device-based/regular/login/?refsrc=https%3A%2F%2Fm.facebook.com%2F&lwv=100&refid=8"
        payload = {
            "lsd": lsd,
            "jazoest": jazoest,
            "m_ts": m_ts,
            "li": li,
            "try_number": try_number,
            "unrecognized_tries": unrecognized_tries,
            "email": self.email,
            "pass": self.password,
            "login": "Iniciar sesión",
            "prefill_contact_point": "",
            "prefill_source": "",
            "prefill_type": "",
            "first_prefill_source": "",
            "first_prefill_type": "",
            "had_cp_prefilled": "false",
            "had_password_prefilled": "false",
            "is_smart_lock": "false",
            "_fb_noscript": "true"
        }
        soup = self.make_request(url_login, method='POST', data=payload, is_soup=True)
        if soup is None:
            raise Exception(f"The login request couldn't be made: {url_login}")

        redirect = soup.select_one('a')
        if not redirect:
            raise Exception("Please log in desktop/mobile Facebook and change your password")

        url_redirect = redirect.get('href', '')
        resp = self.make_request(url_redirect)
        if resp is None:
            raise Exception(f"The login request couldn't be made: {url_redirect}")

        # Finally we get the cookies from the session and save it in a file for future usage
        cookies = self.session.cookies
        f = open(self.cookies_path, 'wb')
        pickle.dump(cookies, f)

        return {'code': 200}

    # Scrap a list of profiles
    def get_posts_from_list(self, profiles):
        data = []
        n = len(profiles)

        for idx in range(n):
            profile = profiles[idx]
            print(f'{idx + 1}/{n}. {profile}')

            posts = self.get_posts_from_profile(profile)
            data.append(posts)

        return data

    # This is the extraction point!
    def update_BigMoneyIndex(self):
        url_profile = 'https://www.facebook.com/programtrading.hk/'
        # Prepare the Url to point to the posts feed
        url_profile = url_profile.replace('www.', 'm.')

        is_group = '/groups/' in url_profile

        # Make a simple GET request
        soup = self.make_request(url_profile)
        if soup is None:
            print(f"Couldn't load the Page: {url_profile}")
            return []

        # Now the extraction...
        css_profile = '.storyStream > div'  # Select the posts from a user profile
        css_page = '#recent > div > div > div'  # Select the posts from a Facebook page
        css_group = '#m_group_stories_container > div > div'  # Select the posts from a Facebook group
        raw_data = soup.select(f'{css_profile} , {css_page} , {css_group}')  # Now join and scrape it
        posts = []
        for item in raw_data:  # Now, for every post...
            html_text = str(item)
            start = html_text.find("mf_story_key")
            end = html_text[start+15:].find('"')
            # find the post id of each post
            post_id = html_text[start+15:start+15+end]
            like_link = "https://m.facebook.com/ufi/reaction/profile/browser/?ft_ent_identifier=%s"%post_id

            description = item.select('p')  # Get list of all p tag, they compose the description

            # Join all the text in p tags, else set empty string
            if len(description) > 0:
                description = '\n'.join([d.get_text() for d in description])
            else:
                description = ''

            if '大戶指數' in description:
                print('大戶指數 found')
                #print(description)
                date_str = description[description.find('】')+2:description.find('】')+12]
                date = datetime.datetime.strptime(date_str,'%Y-%m-%d')
                print('date',date)
                reactions = self.get_number_of_reactions(like_link)
                self.BigMoneyIndex_posts[date] = reactions

    def get_number_of_reactions(self, like_link):
        # https://m.facebook.com/ufi/reaction/profile/browser/?ft_ent_identifier=3344662868912929
        all="reacted to this post"
        soup = self.make_request(like_link)
        # print(like_link)
        text = str(soup)
        start_all = text.find(all)
        reaction_dict = {}

        while True:
            total_count_found = text.find('total_count')
            if total_count_found > 0:

                text = text[text.find('total_count')+12:]
                text_numberOfReaction_end = text.find('&amp')
                numberOfReaction = int(text[:text_numberOfReaction_end])
                text = text[text_numberOfReaction_end:]
                # To determine the type of reaction
                # print(numberOfReaction)

                text_reaction_type = text[:text.find('</span>')]
                # print(text_reaction_type)
                all_type = 'All '+str(numberOfReaction)
                if all_type in text_reaction_type:
                    reaction_type = 'All'
                elif 'alt="Haha"' in text_reaction_type:
                    reaction_type = 'Haha'
                elif 'alt="Like"' in text_reaction_type:
                    reaction_type = 'Like'
                elif 'alt="Care"' in text_reaction_type:
                    reaction_type = 'Care'
                elif 'alt="Love"' in text_reaction_type:
                    reaction_type = 'Love'
                elif 'alt="Love"' in text_reaction_type:
                    reaction_type = 'Wow'
                elif 'alt="Sad"' in text_reaction_type:
                    reaction_type = 'Sad'
                else:
                    reaction_type = 'Unknow'
                reaction_dict[reaction_type] = numberOfReaction
            else:
                break


        return reaction_dict

    def get_latest_post_reaction(self):
        self.update_BigMoneyIndex()
        latest_date = max(self.BigMoneyIndex_posts.keys())
        return self.BigMoneyIndex_posts[latest_date]
