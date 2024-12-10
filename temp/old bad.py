import os
import requests
# import selenium.webdriver as webdriver
import seleniumwire.webdriver as webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# URL = 'https://slideslive.com/embed/presentation/39021924?js_embed_version=3&embed_init_token=eyJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3MzM2NTc5NzAsImV4cCI6MTczMzc4NzU3MCwidSI6eyJ1dWlkIjoiOTM3OTIwYTUtYjRiYS00ZjhkLWIwZDctZWFlYTk0N2ZjZDVkIiwiaSI6bnVsbCwiZSI6bnVsbCwibSI6ZmFsc2V9LCJkIjoiaWNtbC5jYyJ9.LaREBow41ABbzmnAZCZ3O1udZLh7WlZaiIjfIgsuTvs&embed_parent_url=https%3A%2F%2Ficml.cc%2Fvirtual%2F2024%2Ftutorial%2F35227&embed_origin=https%3A%2F%2Ficml.cc&embed_container_id=presentation-embed-39021924&auto_load=true&auto_play=false&zoom_ratio=&disable_fullscreen=false&locale=en&vertical_enabled=true&vertical_enabled_on_mobile=false&allow_hidden_controls_when_paused=true&fit_to_viewport=true&custom_user_id=&user_uuid=937920a5-b4ba-4f8d-b0d7-eaea947fcd5d'
URL = 'https://slideslive.com/embed/presentation/39022942?js_embed_version=3&embed_init_token=eyJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3MzM2NTg2MDEsImV4cCI6MTczMzc4ODIwMSwidSI6eyJ1dWlkIjoiOTM3OTIwYTUtYjRiYS00ZjhkLWIwZDctZWFlYTk0N2ZjZDVkIiwiaSI6bnVsbCwiZSI6bnVsbCwibSI6ZmFsc2V9LCJkIjoiaWNtbC5jYyJ9.KH3D-wSXAaeq22eZiXfjURrvFGW3LQ1se3Y_5BUaumY&embed_parent_url=https%3A%2F%2Ficml.cc%2Fvirtual%2F2024%2F37724&embed_origin=https%3A%2F%2Ficml.cc&embed_container_id=presentation-embed-39022942&auto_load=true&auto_play=false&zoom_ratio=&disable_fullscreen=false&locale=en&vertical_enabled=true&vertical_enabled_on_mobile=false&allow_hidden_controls_when_paused=true&fit_to_viewport=true&custom_user_id=&user_uuid=937920a5-b4ba-4f8d-b0d7-eaea947fcd5d'
DOWNLOADS_DIR = '/Desktop/Work/ICML/'

driver = webdriver.Firefox()
driver.get(URL)

# driver.implicitly_wait(10)
element = WebDriverWait(driver, 20).until(
EC.element_to_be_clickable((By.CLASS_NAME, 'slp__bigButton--next')))

b = driver.find_element(By.CLASS_NAME, 'slp__bigButton--next')

# not working
if False:
    def get_image_url():
        return driver.find_element(By.CSS_SELECTOR, '.slp__slidesPlayer__content > img').get_attribute('src').split('?')[0]
    images_urls = [get_image_url()]
    for i in range(113):
        b.click()
        images_urls.append(get_image_url())

if True:
    for i in range(2): b.click()
    images_urls = list([r.url.split('?')[0] for r in driver.requests if r.method == 'GET' and 'slides/' in r.url])

# For every line in the file
for i, url in enumerate(images_urls):
    # Split on the rightmost / and take everything on the right side of that
    # name = url.rsplit('/', 1)[-1]
    name = f'{i:03}.jpeg'

    r = requests.get(url.replace('small', 'big').replace('medium', 'big'))

    # Combine the name and the downloads directory to get the local filename
    filename = os.path.join(os.getcwd(), name)
    # if not os.path.exists(DOWNLOADS_DIR):
    #     os.makedirs(DOWNLOADS_DIR)
    with open(filename, 'wb') as outfile:
        outfile.write(r.content)