import os
import requests
from bs4 import BeautifulSoup

def scrape_list(url, folder_name, file_name):  #takes target url, output directory, output filename as params
    """
    Find and scrape strings from a url to build a list of user agents
    """

    # Create a folder to store the results
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Generate header, unsophisticated method - implement rotating users in future versions
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) ' +
               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    # try url
    try:
        page = requests.get(url, headers=headers, timeout=5)
    except requests.exceptions.Timeout:
        print(f"Request timed out.")
        return
    #print(f'{url} + status code: {page.status_code} + header: {page.headers}') 
    if page.status_code == 200:
        soup = BeautifulSoup(page.content, 'html.parser')
        #print(f'html: {soup.prettify()}')
        
        # Find all tables - if they exist grab data from each cell, row by row
        tables = soup.find_all('table', class_='table table-striped') # adjust class name as appropriate
        results = 0
        if tables:
            with open(folder_name + '/' + file_name, 'w') as f:
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td') # (['th, td']) to return data and header cells (in case categories/headlines etc useful)
                        if len(cells) > 0:
                            str = cells[0].get_text()
                            results+=1
                            f.write(str + '\n')
                print(f'Wrote {results} items to {folder_name}/{file_name}')
        else:
            print('No tables found on this page!')
    else:
        print(f'Error accessing {url}: Status Code: {page.status_code}')

# call script
scrape_list('URL_Here', 'Folder_Here', 'Output_File.txt')  
